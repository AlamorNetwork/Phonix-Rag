import json
from pathlib import Path

import httpx
import pytest

from app.models.security_finding import Severity
from app.security import manifests
from app.security.scanner import fingerprint, severity_for
from app.security.vuln_intel import Vulnerability, VulnerabilityIntel


# ---------------------------------------------------------------- manifest parsing


def test_requirements_only_yields_pinned_versions(tmp_path: Path):
    """A range cannot be checked against a vulnerability database. Reporting on a version the
    project may not install would produce findings nobody can act on."""
    (tmp_path / "requirements.txt").write_text(
        "requests==2.19.0\n"
        "flask>=2.0            # a range, not a pin\n"
        "django[argon2]==4.2.1\n"
        "# a comment\n"
        "urllib3==1.26.5  # trailing comment\n"
    )
    packages, sources = manifests.collect(tmp_path)

    names = {(p["name"], p["version"]) for p in packages}
    assert names == {("requests", "2.19.0"), ("django", "4.2.1"), ("urllib3", "1.26.5")}
    assert "flask" not in {p["name"] for p in packages}
    assert sources == ["requirements.txt"]


def test_npm_lockfile_is_parsed(tmp_path: Path):
    (tmp_path / "package-lock.json").write_text(
        json.dumps(
            {
                "lockfileVersion": 3,
                "packages": {
                    "": {"name": "root"},
                    "node_modules/lodash": {"version": "4.17.20"},
                    "node_modules/express": {"version": "4.18.2"},
                },
            }
        )
    )
    packages, _ = manifests.collect(tmp_path)
    assert {(p["name"], p["version"]) for p in packages} == {
        ("lodash", "4.17.20"),
        ("express", "4.18.2"),
    }
    assert all(p["ecosystem"] == "npm" for p in packages)


def test_go_mod_is_parsed(tmp_path: Path):
    (tmp_path / "go.mod").write_text(
        "module example.com/x\n\ngo 1.22\n\nrequire (\n"
        "\tgithub.com/gin-gonic/gin v1.9.0\n"
        "\tgolang.org/x/crypto v0.17.0\n)\n"
    )
    packages, _ = manifests.collect(tmp_path)
    assert ("github.com/gin-gonic/gin", "v1.9.0".lstrip("v")) in {
        (p["name"], p["version"]) for p in packages
    }


def test_vendor_directories_are_skipped(tmp_path: Path):
    (tmp_path / "requirements.txt").write_text("requests==2.19.0\n")
    nested = tmp_path / "node_modules" / "somepkg"
    nested.mkdir(parents=True)
    (nested / "package.json").write_text(json.dumps({"dependencies": {"evil": "1.0.0"}}))

    packages, sources = manifests.collect(tmp_path)
    assert sources == ["requirements.txt"], "third-party trees must not be scanned as ours"
    assert "evil" not in {p["name"] for p in packages}


# ---------------------------------------------------------------- severity


def _vuln(**kw) -> Vulnerability:
    base = dict(id="GHSA-x", package="p", version="1.0", ecosystem="PyPI", summary="", severity="low")
    return Vulnerability(**{**base, **kw})


def test_actively_exploited_is_always_critical():
    """The whole point of the KEV catalogue: something being exploited in the wild right now
    outranks whatever band its CVSS score put it in."""
    assert severity_for(_vuln(severity="low", known_exploited=True)) == Severity.CRITICAL


def test_high_epss_escalates_a_low_rated_vulnerability():
    assert severity_for(_vuln(severity="low", epss_score=0.42)) == Severity.HIGH


def test_low_epss_leaves_the_rating_alone():
    assert severity_for(_vuln(severity="low", epss_score=0.001)) == Severity.LOW


def test_epss_never_downgrades_a_severe_vulnerability():
    assert severity_for(_vuln(severity="critical", epss_score=0.0001)) == Severity.CRITICAL


def test_unrated_is_not_treated_as_harmless():
    """An unrated vulnerability is unassessed, not safe - defaulting it to low would quietly
    hide it at the bottom of the list."""
    assert severity_for(_vuln(severity="unknown")) == Severity.MEDIUM


def test_fingerprint_is_stable_and_distinguishes_versions():
    a = fingerprint("proj", "requests", "2.19.0", "GHSA-1")
    assert a == fingerprint("proj", "requests", "2.19.0", "GHSA-1")
    assert a != fingerprint("proj", "requests", "2.20.0", "GHSA-1")
    assert a != fingerprint("proj", "requests", "2.19.0", "GHSA-2")


def test_cve_is_found_among_aliases():
    v = _vuln(id="GHSA-abc", aliases=["CVE-2023-1234", "PYSEC-2023-1"])
    assert v.cve_id == "CVE-2023-1234"


# ---------------------------------------------------------------- intel client


async def test_lookup_enriches_with_kev_and_epss():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/querybatch"):
            return httpx.Response(
                200,
                json={"results": [{"vulns": [{"id": "GHSA-1", "aliases": ["CVE-2021-44228"]}]}]},
            )
        if "known_exploited" in str(request.url):
            return httpx.Response(200, json={"vulnerabilities": [{"cveID": "CVE-2021-44228"}]})
        if "epss" in str(request.url):
            return httpx.Response(200, json={"data": [{"cve": "CVE-2021-44228", "epss": "0.97"}]})
        return httpx.Response(404)

    intel = VulnerabilityIntel(transport=httpx.MockTransport(handler))
    vulns = await intel.lookup([{"name": "log4j", "version": "2.14.1", "ecosystem": "Maven"}])

    assert len(vulns) == 1
    assert vulns[0].known_exploited is True
    assert vulns[0].epss_score == pytest.approx(0.97)
    assert severity_for(vulns[0]) == Severity.CRITICAL


async def test_a_kev_outage_does_not_lose_the_vulnerabilities():
    """Enrichment is a prioritisation signal. Losing it must not lose the findings."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/querybatch"):
            return httpx.Response(200, json={"results": [{"vulns": [{"id": "GHSA-1", "aliases": []}]}]})
        return httpx.Response(500, json={"error": "down"})

    intel = VulnerabilityIntel(transport=httpx.MockTransport(handler))
    vulns = await intel.lookup([{"name": "x", "version": "1.0", "ecosystem": "PyPI"}])

    assert len(vulns) == 1
    assert vulns[0].known_exploited is False


async def test_no_packages_means_no_network_calls():
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("should not have called out for an empty package list")

    intel = VulnerabilityIntel(transport=httpx.MockTransport(handler))
    assert await intel.lookup([]) == []


async def test_exploited_vulnerabilities_are_ordered_first():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/querybatch"):
            return httpx.Response(
                200,
                json={
                    "results": [
                        {"vulns": [{"id": "GHSA-quiet", "aliases": ["CVE-2020-1"]}]},
                        {"vulns": [{"id": "GHSA-hot", "aliases": ["CVE-2021-44228"]}]},
                    ]
                },
            )
        if "known_exploited" in str(request.url):
            return httpx.Response(200, json={"vulnerabilities": [{"cveID": "CVE-2021-44228"}]})
        if "epss" in str(request.url):
            return httpx.Response(200, json={"data": []})
        return httpx.Response(404)

    intel = VulnerabilityIntel(transport=httpx.MockTransport(handler))
    vulns = await intel.lookup(
        [
            {"name": "quiet", "version": "1.0", "ecosystem": "PyPI"},
            {"name": "hot", "version": "2.0", "ecosystem": "PyPI"},
        ]
    )

    assert [v.id for v in vulns][0] == "GHSA-hot", "what is being exploited must come first"
