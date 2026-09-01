import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

import httpx

logger = logging.getLogger(__name__)

OSV_QUERY_URL = "https://api.osv.dev/v1/querybatch"
KEV_URL = "https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json"
EPSS_URL = "https://api.first.org/data/v1/epss"

# CISA's catalogue changes daily at most, and re-fetching a 1MB file per scan is waste.
KEV_TTL = timedelta(hours=6)
EPSS_BATCH = 100
OSV_BATCH = 500


@dataclass
class LookupResult:
    """Whether the lookup actually ran, alongside what it found.

    An empty result means one of two completely different things - the project is clean, or
    we could not reach the database - and a caller that cannot tell them apart will treat an
    outage as an all-clear. Nothing may infer "secure" from "did not find out".
    """

    vulnerabilities: list["Vulnerability"]
    complete: bool
    error: str | None = None


@dataclass
class Vulnerability:
    id: str
    package: str
    version: str
    ecosystem: str
    summary: str
    severity: str
    fixed_versions: list[str] = field(default_factory=list)
    aliases: list[str] = field(default_factory=list)
    known_exploited: bool = False
    epss_score: float | None = None

    @property
    def cve_id(self) -> str | None:
        return next((a for a in [self.id, *self.aliases] if a.startswith("CVE-")), None)


class VulnerabilityIntel:
    """Answers "is this dependency actually vulnerable, and does it actually matter".

    A standard says "use components without known vulnerabilities" but cannot tell you which
    ones those are. This does - and then answers the harder question. A dependency scan on a
    real project returns hundreds of advisories; CISA KEV says which are being exploited in
    the wild right now, and EPSS gives the probability for the rest. Without those two, every
    finding looks equally urgent and the report is noise.

    Runs in the backend, never inside the agent sandbox: the sandbox is deliberately sealed
    with no network, so it parses the manifests and this looks up what it found.
    """

    def __init__(self, timeout: float = 30.0, transport: httpx.BaseTransport | None = None):
        self.timeout = timeout
        self._transport = transport
        self._kev: set[str] = set()
        self._kev_fetched_at: datetime | None = None

    async def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(timeout=self.timeout, transport=self._transport)

    async def lookup(self, packages: list[dict]) -> LookupResult:
        """`packages` is [{"name": ..., "version": ..., "ecosystem": ...}, ...]."""
        if not packages:
            return LookupResult(vulnerabilities=[], complete=True)

        vulns, failures = await self._query_osv(packages)
        if failures:
            # A partial answer is not an answer. Reporting what we happened to get would let a
            # caller conclude that everything else is clean.
            return LookupResult(
                vulnerabilities=vulns,
                complete=False,
                error=f"{failures} OSV request(s) failed; results are incomplete",
            )
        if not vulns:
            return LookupResult(vulnerabilities=[], complete=True)

        # Hydrate first, and not as an optional extra: querybatch returns only {id, modified},
        # so until the detail records are fetched a vulnerability has no aliases and therefore
        # no CVE id. KEV and EPSS both match on CVE id, so enriching before this point matches
        # nothing at all - silently, which is worse than failing.
        await self.hydrate(vulns)

        # Enrichment is best-effort: a KEV or EPSS outage must not lose the vulnerabilities
        # themselves, only the prioritisation signal.
        await asyncio.gather(
            self._mark_known_exploited(vulns),
            self._attach_epss(vulns),
            return_exceptions=True,
        )
        vulns = _deduplicate(vulns)
        vulns.sort(key=lambda v: (not v.known_exploited, -(v.epss_score or 0.0)))
        return LookupResult(vulnerabilities=vulns, complete=True)

    async def _query_osv(self, packages: list[dict]) -> tuple[list[Vulnerability], int]:
        queries = [
            {
                "package": {"name": p["name"], "ecosystem": p.get("ecosystem", "PyPI")},
                "version": p["version"],
            }
            for p in packages
            if p.get("name") and p.get("version")
        ]
        if not queries:
            return [], 0

        found: list[Vulnerability] = []
        failures = 0
        async with await self._client() as client:
            for start in range(0, len(queries), OSV_BATCH):
                chunk = queries[start : start + OSV_BATCH]
                try:
                    response = await client.post(OSV_QUERY_URL, json={"queries": chunk})
                    response.raise_for_status()
                    results = response.json().get("results", [])
                except Exception:
                    logger.exception("OSV lookup failed for a batch of %d packages", len(chunk))
                    failures += 1
                    continue

                for query, result in zip(chunk, results):
                    for entry in result.get("vulns") or []:
                        found.append(
                            Vulnerability(
                                id=entry.get("id", "unknown"),
                                package=query["package"]["name"],
                                version=query["version"],
                                ecosystem=query["package"]["ecosystem"],
                                # querybatch returns ids only; the detail call fills these in.
                                summary=entry.get("summary", ""),
                                severity="unknown",
                                aliases=entry.get("aliases") or [],
                            )
                        )
        return found, failures

    async def hydrate(self, vulns: list[Vulnerability]) -> list[Vulnerability]:
        """Fetch the full record for each vulnerability. querybatch returns ids and little
        else, which is fast but not enough to write a finding a human can act on."""
        async with await self._client() as client:

            async def one(v: Vulnerability) -> None:
                try:
                    response = await client.get(f"https://api.osv.dev/v1/vulns/{v.id}")
                    response.raise_for_status()
                    data = response.json()
                except Exception:
                    return
                v.summary = data.get("summary") or data.get("details", "")[:300] or v.summary
                v.aliases = data.get("aliases") or v.aliases
                v.severity = _severity_from_osv(data)
                v.fixed_versions = _fixed_versions(data, v.package)

            await asyncio.gather(*(one(v) for v in vulns), return_exceptions=True)
        return vulns

    async def _mark_known_exploited(self, vulns: list[Vulnerability]) -> None:
        kev = await self._load_kev()
        for v in vulns:
            cve = v.cve_id
            if cve and cve in kev:
                v.known_exploited = True

    async def _load_kev(self) -> set[str]:
        fresh = self._kev_fetched_at and datetime.now(timezone.utc) - self._kev_fetched_at < KEV_TTL
        if self._kev and fresh:
            return self._kev
        try:
            async with await self._client() as client:
                response = await client.get(KEV_URL)
                response.raise_for_status()
                data = response.json()
            self._kev = {item["cveID"] for item in data.get("vulnerabilities", []) if item.get("cveID")}
            self._kev_fetched_at = datetime.now(timezone.utc)
            logger.info("loaded CISA KEV: %d actively exploited CVEs", len(self._kev))
        except Exception:
            logger.exception("could not refresh CISA KEV; keeping %d cached entries", len(self._kev))
        return self._kev

    async def _attach_epss(self, vulns: list[Vulnerability]) -> None:
        cves = sorted({v.cve_id for v in vulns if v.cve_id})
        if not cves:
            return
        scores: dict[str, float] = {}
        async with await self._client() as client:
            for start in range(0, len(cves), EPSS_BATCH):
                chunk = cves[start : start + EPSS_BATCH]
                try:
                    response = await client.get(EPSS_URL, params={"cve": ",".join(chunk)})
                    response.raise_for_status()
                    for row in response.json().get("data", []):
                        scores[row["cve"]] = float(row["epss"])
                except Exception:
                    logger.exception("EPSS lookup failed for %d CVEs", len(chunk))
        for v in vulns:
            if v.cve_id in scores:
                v.epss_score = scores[v.cve_id]


def _severity_from_osv(data: dict) -> str:
    """OSV reports severity inconsistently across ecosystems; prefer the explicit database
    rating and fall back to the CVSS vector's own wording."""
    for entry in data.get("database_specific", {}), *(data.get("affected") or []):
        raw = (entry or {}).get("database_specific", {}).get("severity") or (entry or {}).get("severity")
        if isinstance(raw, str) and raw.lower() in {"critical", "high", "medium", "moderate", "low"}:
            return "medium" if raw.lower() == "moderate" else raw.lower()
    return "unknown"


def _fixed_versions(data: dict, package: str) -> list[str]:
    fixed: list[str] = []
    for affected in data.get("affected") or []:
        if affected.get("package", {}).get("name") != package:
            continue
        for rng in affected.get("ranges") or []:
            for event in rng.get("events") or []:
                if "fixed" in event:
                    fixed.append(event["fixed"])
    return sorted(set(fixed))


vuln_intel = VulnerabilityIntel()


# Worst-first, so merging two advisories keeps the more serious rating.
_SEVERITY_RANK = {"critical": 0, "high": 1, "medium": 2, "moderate": 2, "low": 3, "unknown": 4}


def _deduplicate(vulns: list[Vulnerability]) -> list[Vulnerability]:
    """Collapse advisories that describe the same vulnerability in the same package.

    OSV routinely returns several records for one underlying flaw - a GHSA and a PYSEC entry
    for the same CVE, for instance - and they do not always agree on severity. Reported
    separately, the same problem appears twice with two different ratings, which reads as
    noise and makes the severity counts wrong. Keeping the worst rating is the safe direction
    to merge in.
    """
    merged: dict[tuple, Vulnerability] = {}

    for vuln in vulns:
        # Only a shared CVE proves two advisories are the same issue. Without one, the
        # advisory id has to stand on its own rather than being guessed at.
        key = (vuln.package, vuln.version, vuln.cve_id or vuln.id)
        current = merged.get(key)
        if current is None:
            merged[key] = vuln
            continue

        if _SEVERITY_RANK.get(vuln.severity, 4) < _SEVERITY_RANK.get(current.severity, 4):
            current.severity = vuln.severity
        current.known_exploited = current.known_exploited or vuln.known_exploited
        if current.epss_score is None:
            current.epss_score = vuln.epss_score
        current.aliases = sorted({*current.aliases, *vuln.aliases, vuln.id})
        current.fixed_versions = sorted({*current.fixed_versions, *vuln.fixed_versions})
        if len(vuln.summary) > len(current.summary):
            current.summary = vuln.summary

    return list(merged.values())
