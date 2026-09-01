from sqlalchemy import Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base
from app.database.types import ID_LENGTH, IdMixin, TimestampMixin


class Severity:
    """Ordered worst-first, which is the order a human wants to read them in."""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"

    ORDER = [CRITICAL, HIGH, MEDIUM, LOW, INFO]

    @classmethod
    def rank(cls, severity: str) -> int:
        return cls.ORDER.index(severity) if severity in cls.ORDER else len(cls.ORDER)


class FindingStatus:
    OPEN = "open"
    FIXED = "fixed"
    ACCEPTED = "accepted"      # a human decided to live with it
    FALSE_POSITIVE = "false_positive"
    REGRESSED = "regressed"    # was fixed, came back


class FindingSource:
    DEPENDENCY = "dependency"   # a known-vulnerable package, from OSV
    ASVS = "asvs"               # an ASVS requirement judged not met
    SECRET = "secret"           # a credential found in the tree
    CONTAINER = "container"     # CIS Docker
    AGENTIC = "agentic"         # OWASP Agentic Top 10
    REVIEW = "review"           # raised by an agent's own reading


class SecurityFinding(Base, IdMixin, TimestampMixin):
    """One security problem, in a form a human can act on and a later scan can match again.

    Deliberately carries the *external* identifier (an ASVS shortcode, a GHSA/CVE id) rather
    than only our own: it is what lets a finding be looked up, compared across tools, and
    recognised as the same issue on the next scan instead of being reported afresh.
    """

    __tablename__ = "security_findings"

    project_id: Mapped[str] = mapped_column(String(ID_LENGTH), ForeignKey("projects.id"), index=True)
    agent_run_id: Mapped[str | None] = mapped_column(String(ID_LENGTH), nullable=True)

    source: Mapped[str] = mapped_column(String(32), index=True)
    # The identifier in whatever catalogue this came from: "V6.1.1", "GHSA-9hjg-9r4m-mvj7".
    external_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    cve_id: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)

    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text, default="")
    severity: Mapped[str] = mapped_column(String(16), index=True)
    status: Mapped[str] = mapped_column(String(24), default=FindingStatus.OPEN, index=True)

    # Where it is. A finding without a location is not actionable.
    component: Mapped[str | None] = mapped_column(String(255), nullable=True)
    file_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    line: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # What proves it. The spec is explicit that no review may just say "looks good", and the
    # same rule applies in reverse: a finding without evidence is an assertion, not a finding.
    evidence: Mapped[str] = mapped_column(Text, default="")
    remediation: Mapped[str] = mapped_column(Text, default="")

    # Exploitation reality, not just theoretical severity. A scan can return hundreds of
    # vulnerabilities; these two fields are what separate the handful that matter.
    # Whether CISA lists it as being exploited in the wild right now.
    known_exploited: Mapped[bool] = mapped_column(default=False, index=True)
    # EPSS: probability of exploitation in the next 30 days, 0..1.
    epss_score: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Stable across scans, so the same problem is recognised rather than re-reported.
    fingerprint: Mapped[str] = mapped_column(String(64), index=True)
