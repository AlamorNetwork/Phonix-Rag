import hashlib
import logging
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.models.security_finding import FindingSource, FindingStatus, SecurityFinding, Severity
from app.security import manifests
from app.security.vuln_intel import Vulnerability, VulnerabilityIntel

logger = logging.getLogger(__name__)

# OSV's own rating, mapped onto ours. "unknown" is deliberately not silently downgraded to
# low - an unrated vulnerability is unassessed, not harmless.
_OSV_TO_SEVERITY = {
    "critical": Severity.CRITICAL,
    "high": Severity.HIGH,
    "medium": Severity.MEDIUM,
    "low": Severity.LOW,
    "unknown": Severity.MEDIUM,
}

# EPSS above this means exploitation is genuinely likely, not theoretical.
EPSS_ESCALATION = 0.10


def fingerprint(*parts: str) -> str:
    """Stable across scans so the same problem is recognised instead of re-reported."""
    return hashlib.sha256("|".join(parts).encode()).hexdigest()[:32]


def severity_for(vuln: Vulnerability) -> str:
    """Rate by what is actually true of this vulnerability today.

    A vulnerability CISA lists as exploited in the wild is critical regardless of its CVSS
    band - that is the whole point of the KEV catalogue. A high EPSS score raises a finding
    for the same reason: it is being exploited, or about to be.
    """
    base = _OSV_TO_SEVERITY.get(vuln.severity, Severity.MEDIUM)
    if vuln.known_exploited:
        return Severity.CRITICAL
    if (vuln.epss_score or 0) >= EPSS_ESCALATION and Severity.rank(base) > Severity.rank(Severity.HIGH):
        return Severity.HIGH
    return base


def _describe(vuln: Vulnerability) -> tuple[str, str, str]:
    title = f"{vuln.package} {vuln.version} — {vuln.id}"

    evidence_lines = [
        f"Package: {vuln.package}=={vuln.version} ({vuln.ecosystem})",
        f"Advisory: {vuln.id}",
    ]
    if vuln.cve_id and vuln.cve_id != vuln.id:
        evidence_lines.append(f"CVE: {vuln.cve_id}")
    if vuln.known_exploited:
        evidence_lines.append("CISA KEV: listed as exploited in the wild")
    if vuln.epss_score is not None:
        evidence_lines.append(f"EPSS: {vuln.epss_score:.4f} probability of exploitation in 30 days")
    evidence_lines.append(f"Source: https://osv.dev/vulnerability/{vuln.id}")

    if vuln.fixed_versions:
        remediation = f"Upgrade {vuln.package} to {' or '.join(vuln.fixed_versions)} or later."
    else:
        remediation = (
            f"No fixed version is published for {vuln.package}. Assess whether the affected "
            "code path is reachable, and consider replacing the dependency."
        )
    return title, "\n".join(evidence_lines), remediation


class DependencyScanner:
    """Finds known-vulnerable dependencies in a workspace.

    The two halves are deliberately separate: parsing manifests only reads files and could run
    inside the sealed sandbox, while looking vulnerabilities up needs the network and runs
    here. Keeping the lookup out of the sandbox is what lets the sandbox stay network-less.
    """

    def __init__(self, session_maker: async_sessionmaker, intel: VulnerabilityIntel):
        self.session_maker = session_maker
        self.intel = intel

    async def scan(self, project_id: str, workspace_root: Path, agent_run_id: str | None = None) -> dict:
        packages, sources = manifests.collect(workspace_root)
        if not packages:
            return {"packages_scanned": 0, "manifests": [], "findings": [], "new": 0, "resolved": 0}

        # lookup() hydrates and enriches before returning; the results arrive fully rated and
        # already ordered with anything exploited in the wild first.
        result = await self.intel.lookup(packages)
        vulns = result.vulnerabilities

        summary = await self._record(project_id, vulns, agent_run_id, complete=result.complete)
        summary.update(
            {
                "packages_scanned": len(packages),
                "manifests": sources,
                "complete": result.complete,
                "error": result.error,
            }
        )
        return summary

    async def _record(
        self, project_id: str, vulns: list[Vulnerability], agent_run_id: str | None, *, complete: bool
    ) -> dict:
        seen: set[str] = set()
        reported: list[dict] = []
        new_count = 0

        async with self.session_maker() as db:
            existing = {
                f.fingerprint: f
                for f in (
                    await db.execute(
                        select(SecurityFinding).where(
                            SecurityFinding.project_id == project_id,
                            SecurityFinding.source == FindingSource.DEPENDENCY,
                        )
                    )
                )
                .scalars()
                .all()
            }

            for vuln in vulns:
                fp = fingerprint(project_id, vuln.package, vuln.version, vuln.id)
                seen.add(fp)
                severity = severity_for(vuln)
                title, evidence, remediation = _describe(vuln)

                finding = existing.get(fp)
                if finding is None:
                    finding = SecurityFinding(
                        project_id=project_id,
                        agent_run_id=agent_run_id,
                        source=FindingSource.DEPENDENCY,
                        external_id=vuln.id,
                        cve_id=vuln.cve_id,
                        title=title,
                        description=vuln.summary or title,
                        severity=severity,
                        status=FindingStatus.OPEN,
                        component=f"{vuln.package}=={vuln.version}",
                        evidence=evidence,
                        remediation=remediation,
                        known_exploited=vuln.known_exploited,
                        epss_score=vuln.epss_score,
                        fingerprint=fp,
                    )
                    db.add(finding)
                    new_count += 1
                else:
                    # A finding that was fixed and is present again is a regression, which is
                    # a different thing from one that was never addressed.
                    if finding.status in (FindingStatus.FIXED, FindingStatus.REGRESSED):
                        finding.status = FindingStatus.REGRESSED
                    finding.severity = severity
                    finding.evidence = evidence
                    finding.remediation = remediation
                    finding.known_exploited = vuln.known_exploited
                    finding.epss_score = vuln.epss_score

                reported.append(
                    {
                        "id": vuln.id,
                        "package": vuln.package,
                        "version": vuln.version,
                        "severity": severity,
                        "known_exploited": vuln.known_exploited,
                        "epss": vuln.epss_score,
                        "fix": vuln.fixed_versions,
                    }
                )

            # Only a scan that actually completed may close anything. On an incomplete scan
            # the absence of a vulnerability means "we did not find out", not "it is gone" -
            # closing findings there would report an outage as an all-clear.
            resolved = 0
            if complete:
                for fp, finding in existing.items():
                    if fp not in seen and finding.status in (FindingStatus.OPEN, FindingStatus.REGRESSED):
                        finding.status = FindingStatus.FIXED
                        resolved += 1

            await db.commit()

        return {"findings": reported, "new": new_count, "resolved": resolved}
