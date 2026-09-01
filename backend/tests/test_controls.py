from pathlib import Path

import httpx
import pytest
from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.database.base import Base
from app.models.control_assessment import AssessmentResult, SecurityControl, VerificationMethod
from app.security import evidence, frameworks

ASVS_SAMPLE = {
    "Name": "OWASP Application Security Verification Standard",
    "Version": "5.0.0",
    "Requirements": [
        {
            "Shortcode": "V6",
            "Name": "Authentication",
            "Items": [
                {
                    "Shortcode": "V6.1",
                    "Name": "Authentication Documentation",
                    "Items": [
                        {
                            "Shortcode": "V6.1.1",
                            "Description": "Verify that application documentation defines how rate limiting is used.",
                            "L": "1",
                        }
                    ],
                },
                {
                    "Shortcode": "V6.2",
                    "Name": "Password Security",
                    "Items": [
                        {
                            "Shortcode": "V6.2.1",
                            "Description": "Verify that user set passwords are at least 8 characters in length.",
                            "L": "1",
                        }
                    ],
                },
            ],
        },
        {
            "Shortcode": "V12",
            "Name": "Secure Communication",
            "Items": [
                {
                    "Shortcode": "V12.1",
                    "Name": "TLS",
                    "Items": [
                        {
                            "Shortcode": "V12.1.1",
                            "Description": "Verify that TLS is configured with only strong cipher suites.",
                            "L": "1",
                        }
                    ],
                }
            ],
        },
    ],
}


@pytest.fixture
async def db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")

    @event.listens_for(engine.sync_engine, "connect")
    def _wal(conn, _rec):
        cur = conn.cursor()
        cur.execute("PRAGMA journal_mode=WAL")
        cur.close()

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sm = async_sessionmaker(engine, expire_on_commit=False)
    async with sm() as session:
        yield session
    await engine.dispose()


# ---------------------------------------------------------------- the core rule


def test_unknown_is_not_satisfied():
    """The single rule this whole layer exists to enforce: a control nobody could evaluate is
    not a control that passed. If these collapse, every gap in the tooling reads as
    compliance."""
    assert AssessmentResult.UNKNOWN not in AssessmentResult.SATISFIED
    assert AssessmentResult.NEEDS_HUMAN_REVIEW not in AssessmentResult.SATISFIED
    assert AssessmentResult.PARTIAL not in AssessmentResult.SATISFIED
    assert AssessmentResult.FAIL not in AssessmentResult.SATISFIED


def test_only_a_pass_or_a_genuine_exemption_counts_as_satisfied():
    assert AssessmentResult.PASS in AssessmentResult.SATISFIED
    assert AssessmentResult.NOT_APPLICABLE in AssessmentResult.SATISFIED
    assert len(AssessmentResult.SATISFIED) == 2


# ---------------------------------------------------------------- verification classification


def test_documentation_requirements_are_routed_to_a_human():
    """An agent that thinks it can verify a documentation requirement will produce a
    confident, wrong pass - the expensive direction to be wrong in."""
    methods = frameworks.classify_verification(
        "Verify that application documentation defines how rate limiting is used.", "V6"
    )
    assert methods == [VerificationMethod.HUMAN_REVIEW]


@pytest.mark.parametrize(
    "requirement",
    [
        "Verify that the threat model is kept up to date.",
        "Verify that the architecture separates trust boundaries.",
        "Verify that business logic flows are processed in order.",
        "Verify that each deviation is justified and approved by the security team.",
    ],
)
def test_design_and_process_requirements_are_routed_to_a_human(requirement: str):
    assert frameworks.classify_verification(requirement, "V1") == [VerificationMethod.HUMAN_REVIEW]


def test_tls_requirements_are_marked_config_checkable():
    methods = frameworks.classify_verification(
        "Verify that TLS is configured with only strong cipher suites.", "V12"
    )
    assert VerificationMethod.CONFIG_INSPECTION in methods


def test_dependency_requirements_are_marked_scannable():
    methods = frameworks.classify_verification(
        "Verify that all components are free of known vulnerable versions.", "V15"
    )
    assert VerificationMethod.DEPENDENCY_SCAN in methods


def test_an_unrecognised_requirement_defaults_to_human_not_automatic():
    """Defaulting the other way would let anything the classifier does not understand be
    silently claimed as machine-verifiable."""
    methods = frameworks.classify_verification("Verify that the widget frobnicates safely.", "V99")
    assert methods == [VerificationMethod.HUMAN_REVIEW]


# ---------------------------------------------------------------- ASVS parsing


def test_asvs_json_is_flattened_with_its_own_identifiers():
    controls = frameworks.parse_asvs(ASVS_SAMPLE)

    assert len(controls) == 3
    ids = {c["control_id"] for c in controls}
    assert ids == {"V6.1.1", "V6.2.1", "V12.1.1"}

    auth = next(c for c in controls if c["control_id"] == "V6.2.1")
    assert auth["framework"] == "OWASP-ASVS"
    assert auth["framework_version"] == "5.0.0"
    assert auth["chapter"] == "V6 Authentication"
    assert auth["section"] == "Password Security"
    assert auth["level"] == "1"


def test_documentation_control_is_classified_as_human_on_import():
    controls = frameworks.parse_asvs(ASVS_SAMPLE)
    doc_control = next(c for c in controls if c["control_id"] == "V6.1.1")
    assert doc_control["verification"] == [VerificationMethod.HUMAN_REVIEW]


async def test_import_is_idempotent(db):
    controls = frameworks.parse_asvs(ASVS_SAMPLE)

    first = await frameworks.import_controls(db, controls)
    assert first["imported"] == 3

    second = await frameworks.import_controls(db, controls)
    assert second["imported"] == 0, "re-importing a framework must not duplicate it"
    assert second["updated"] == 3

    rows = (await db.execute(select(SecurityControl))).scalars().all()
    assert len(rows) == 3


async def test_reimport_updates_changed_requirement_text(db):
    await frameworks.import_controls(db, frameworks.parse_asvs(ASVS_SAMPLE))

    revised = frameworks.parse_asvs(ASVS_SAMPLE)
    for c in revised:
        if c["control_id"] == "V6.2.1":
            c["requirement"] = "Verify that user set passwords are at least 12 characters in length."

    await frameworks.import_controls(db, revised)

    row = (
        await db.execute(select(SecurityControl).where(SecurityControl.control_id == "V6.2.1"))
    ).scalar_one()
    assert "12 characters" in row.requirement


async def test_fetching_asvs_parses_the_real_shape():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=ASVS_SAMPLE)

    document = await frameworks.fetch_asvs(transport=httpx.MockTransport(handler))
    assert len(frameworks.parse_asvs(document)) == 3


# ---------------------------------------------------------------- evidence


def test_evidence_masks_secrets_before_storage():
    """Evidence records config files and command output verbatim, which is exactly where a
    key lives."""
    item = evidence.from_command(
        ["printenv"], 0, "LIARA_API_KEY=sk-abcdefghijklmnop1234567890", ""
    )
    stored = item.to_dict()
    assert "sk-abcdefghijklmnop1234567890" not in stored["observations"]["output"]


def test_absence_is_recorded_as_its_own_kind_of_evidence():
    """Having looked and found nothing is different from never having looked - which is the
    whole reason UNKNOWN exists as a result."""
    item = evidence.from_absence("a Content-Security-Policy header", "nginx.conf")
    assert item.type == evidence.EvidenceType.ABSENCE
    assert "not found" in item.summary


def test_digest_identifies_content_without_storing_it():
    a = evidence.digest("password = hunter2")
    assert a == evidence.digest("password = hunter2")
    assert a != evidence.digest("password = hunter3")
    assert "hunter2" not in a
