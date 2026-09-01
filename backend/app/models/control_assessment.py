from sqlalchemy import JSON, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base
from app.database.types import ID_LENGTH, IdMixin, TimestampMixin


class AssessmentResult:
    """What we actually concluded about a control.

    The distinction that matters is between FAIL and UNKNOWN. A control nobody could evaluate
    is not a control that passed - if the two collapse together, every gap in the tooling
    quietly reads as compliance, which is the single most dangerous thing an automated
    security reviewer can do.
    """

    PASS = "pass"
    FAIL = "fail"
    PARTIAL = "partial"                    # some sub-checks hold, others do not
    UNKNOWN = "unknown"                    # could not be determined; explicitly not a pass
    NOT_APPLICABLE = "not_applicable"      # the control does not apply to this project
    NEEDS_HUMAN_REVIEW = "needs_human_review"  # only a person can judge this

    # Anything not in here has not been shown to hold.
    SATISFIED = {PASS, NOT_APPLICABLE}

    ALL = [PASS, FAIL, PARTIAL, UNKNOWN, NOT_APPLICABLE, NEEDS_HUMAN_REVIEW]


class VerificationMethod:
    STATIC_ANALYSIS = "static_analysis"
    DEPENDENCY_SCAN = "dependency_scan"
    RUNTIME_TEST = "runtime_test"
    CONFIG_INSPECTION = "config_inspection"
    HUMAN_REVIEW = "human_review"


class SecurityControl(Base, IdMixin, TimestampMixin):
    """One requirement from an external framework, normalised.

    Frameworks are ingested rather than hard-coded so a new release - ASVS 5.0.1, a newer CIS
    benchmark, next year's Agentic Top 10 - is a re-import rather than a rewrite. The
    framework's own identifier is kept verbatim, because that is what makes a result
    comparable with other tools and traceable back to the published standard.
    """

    __tablename__ = "security_controls"

    framework: Mapped[str] = mapped_column(String(64), index=True)      # "OWASP-ASVS"
    framework_version: Mapped[str] = mapped_column(String(32))          # "5.0.0"
    # The identifier as the standard writes it: "V6.1.1", "CIS-Docker-4.1", "ASI01".
    control_id: Mapped[str] = mapped_column(String(64), index=True)
    chapter: Mapped[str] = mapped_column(String(128), default="")
    section: Mapped[str] = mapped_column(String(128), default="")
    requirement: Mapped[str] = mapped_column(Text)
    # ASVS levels 1-3; other frameworks use their own tiering, kept as given.
    level: Mapped[str | None] = mapped_column(String(16), nullable=True, index=True)
    # How this could be checked, and therefore whether an agent can check it at all.
    verification: Mapped[list] = mapped_column(JSON, default=list)
    # Cross-references to other frameworks, e.g. {"cwe": ["CWE-521"]}.
    mappings: Mapped[dict] = mapped_column(JSON, default=dict)


class ControlAssessment(Base, IdMixin, TimestampMixin):
    """The result of evaluating one control against one project, with its evidence.

    Separate from SecurityFinding on purpose: a finding says something is wrong, while an
    assessment records that a control was looked at and what was concluded - including that
    nothing could be concluded. Without this, "we never checked" and "we checked and it was
    fine" are indistinguishable, because both produce no finding.
    """

    __tablename__ = "control_assessments"

    project_id: Mapped[str] = mapped_column(String(ID_LENGTH), ForeignKey("projects.id"), index=True)
    control_id: Mapped[str] = mapped_column(String(ID_LENGTH), ForeignKey("security_controls.id"), index=True)
    agent_run_id: Mapped[str | None] = mapped_column(String(ID_LENGTH), nullable=True)

    result: Mapped[str] = mapped_column(String(24), index=True)
    method: Mapped[str] = mapped_column(String(32))
    # Why we concluded what we concluded. Required for every result, including a pass: the
    # spec's rule that no review may simply say "looks good" applies to machines too.
    rationale: Mapped[str] = mapped_column(Text, default="")
    # Typed evidence records rather than a prose blob, so a later run can compare them and a
    # human can see exactly what was observed. See app/security/evidence.py.
    evidence: Mapped[list] = mapped_column(JSON, default=list)
    # How much to trust this result, 0..1. An agent's reading of code is not a proof.
    confidence: Mapped[float] = mapped_column(default=0.0)
    # Set when the assessment produced a finding, so the two views stay connected.
    finding_id: Mapped[str | None] = mapped_column(String(ID_LENGTH), nullable=True)
