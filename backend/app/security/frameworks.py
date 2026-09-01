import json
import logging
from pathlib import Path

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.control_assessment import SecurityControl, VerificationMethod

logger = logging.getLogger(__name__)

ASVS_VERSION = "5.0.0"
ASVS_JSON_URL = (
    "https://raw.githubusercontent.com/OWASP/ASVS/master/5.0/docs_en/"
    "OWASP_Application_Security_Verification_Standard_5.0.0_en.json"
)

# Wording that marks a requirement as being about documentation, design intent or human
# process. These win over everything below: an agent can read about a threat model, but it
# cannot verify one.
_HUMAN_SIGNALS = (
    "documentation",
    "documented",
    "threat model",
    "architecture",
    "business logic",
    "policy",
    "approved by",
    "justif",
    "risk assessment",
    "trained",
    "process is in place",
)

# Concrete, checkable things a requirement can talk about. Classification keys off these
# rather than off which chapter a requirement lives in: the chapter says what area it belongs
# to, not whether the property it asserts is observable. Keying off the chapter routed almost
# all of Authentication to a human, including "the nonce is at least 64 bits" - which is
# exactly the kind of thing a machine checks better than a person.
_CONFIG_SIGNALS = (
    "header", "tls", "ssl", "cookie", "cipher", "certificate", "configur", "http",
    "cors", "same-site", "samesite", "secure flag", "httponly", "port", "protocol",
)
_DEPENDENCY_SIGNALS = ("dependency", "dependencies", "component", "library", "package", "third-party")
_CODE_SIGNALS = (
    "encod", "escap", "sanitiz", "validat", "parameteriz", "hash", "bcrypt", "argon2",
    "pbkdf2", "scrypt", "signature", "mac ", "token", "session", "timeout", "expir",
    "random", "entropy", "nonce", "salt", "iteration", "algorithm", "encrypt", "decrypt",
    "key length", "bits", "characters in length", "rate limit", "logged", "log ",
    "redirect", "upload", "deserializ", "injection", "query", "permission", "revoke",
)

# A stated threshold is the clearest sign of something measurable: "at least 8 characters",
# "minimum of 128 bits", "no longer than 30 minutes".
_THRESHOLD_SIGNALS = ("at least", "minimum", "no longer than", "no more than", "at most", "maximum")


def classify_verification(requirement: str, chapter: str = "") -> list[str]:
    """How this control could be checked - and therefore whether an agent can check it.

    Getting this wrong in the permissive direction is the expensive mistake: an agent that
    believes it can verify a design requirement will produce a confident, wrong pass. So the
    human signals override everything, and anything that matches nothing at all still falls
    through to a human rather than being optimistically claimed as automatable.
    """
    text = requirement.lower()

    if any(signal in text for signal in _HUMAN_SIGNALS):
        return [VerificationMethod.HUMAN_REVIEW]

    methods: list[str] = []
    if any(word in text for word in _DEPENDENCY_SIGNALS):
        methods.append(VerificationMethod.DEPENDENCY_SCAN)
    if any(word in text for word in _CONFIG_SIGNALS):
        methods.append(VerificationMethod.CONFIG_INSPECTION)
    if any(word in text for word in _CODE_SIGNALS) or any(t in text for t in _THRESHOLD_SIGNALS):
        methods.append(VerificationMethod.STATIC_ANALYSIS)

    # Nothing matched, so nothing here justifies claiming it can be checked automatically.
    return methods or [VerificationMethod.HUMAN_REVIEW]


def parse_asvs(document: dict) -> list[dict]:
    """Flatten the official ASVS JSON into control rows.

    Uses the published structure as-is: chapters contain sections contain items, each with a
    Shortcode, the requirement text, and its level.
    """
    controls: list[dict] = []
    for chapter in document.get("Requirements", []):
        chapter_code = chapter.get("Shortcode", "")
        chapter_name = chapter.get("Name", "")
        for section in chapter.get("Items", []):
            section_name = section.get("Name", "")
            for item in section.get("Items", []):
                shortcode = item.get("Shortcode")
                requirement = item.get("Description", "")
                if not shortcode or not requirement:
                    continue
                controls.append(
                    {
                        "framework": "OWASP-ASVS",
                        "framework_version": document.get("Version", ASVS_VERSION),
                        "control_id": shortcode,
                        "chapter": f"{chapter_code} {chapter_name}".strip(),
                        "section": section_name,
                        "requirement": requirement,
                        "level": str(item.get("L", "")) or None,
                        "verification": classify_verification(requirement, chapter_code),
                        "mappings": {},
                    }
                )
    return controls


async def fetch_asvs(timeout: float = 60.0, transport: httpx.BaseTransport | None = None) -> dict:
    async with httpx.AsyncClient(timeout=timeout, transport=transport) as client:
        response = await client.get(ASVS_JSON_URL)
        response.raise_for_status()
        return response.json()


def load_asvs_from_file(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


async def import_controls(db: AsyncSession, controls: list[dict]) -> dict:
    """Upsert controls by (framework, version, control_id).

    Idempotent so re-importing a framework is safe, and so a new release of a standard is an
    import rather than a migration.
    """
    if not controls:
        return {"imported": 0, "updated": 0, "total": 0}

    framework = controls[0]["framework"]
    version = controls[0]["framework_version"]

    existing = {
        c.control_id: c
        for c in (
            await db.execute(
                select(SecurityControl).where(
                    SecurityControl.framework == framework,
                    SecurityControl.framework_version == version,
                )
            )
        )
        .scalars()
        .all()
    }

    imported = updated = 0
    for row in controls:
        current = existing.get(row["control_id"])
        if current is None:
            db.add(SecurityControl(**row))
            imported += 1
        else:
            current.requirement = row["requirement"]
            current.chapter = row["chapter"]
            current.section = row["section"]
            current.level = row["level"]
            current.verification = row["verification"]
            updated += 1

    await db.commit()
    logger.info(
        "imported %s %s: %d new, %d updated", framework, version, imported, updated
    )
    return {"imported": imported, "updated": updated, "total": len(controls)}
