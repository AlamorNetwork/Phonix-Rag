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

# Chapters whose requirements are mostly about how something is configured or written, and so
# are within reach of a static or configuration check. The rest lean on design intent, which
# an agent can read about but cannot verify.
_MECHANICAL_CHAPTERS = {"V1", "V3", "V4", "V9", "V11", "V12", "V13", "V16"}

# Wording that marks a requirement as being about documentation, design or human process.
# These are the ones an agent must hand back rather than guess at.
_HUMAN_SIGNALS = (
    "documentation",
    "documented",
    "threat model",
    "architecture",
    "design",
    "business logic",
    "policy",
    "approved by",
    "justif",
)


def classify_verification(requirement: str, chapter: str) -> list[str]:
    """How this control could be checked - and therefore whether an agent can check it.

    Getting this wrong in the permissive direction is the expensive mistake: an agent that
    believes it can verify a design requirement will produce a confident, wrong pass.
    """
    text = requirement.lower()

    if any(signal in text for signal in _HUMAN_SIGNALS):
        return [VerificationMethod.HUMAN_REVIEW]

    methods: list[str] = []
    if any(word in text for word in ("dependency", "component", "library", "package", "version")):
        methods.append(VerificationMethod.DEPENDENCY_SCAN)
    if any(word in text for word in ("header", "tls", "cookie", "cipher", "certificate", "configur")):
        methods.append(VerificationMethod.CONFIG_INSPECTION)
    if chapter in _MECHANICAL_CHAPTERS:
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
