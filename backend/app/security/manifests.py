import json
import re
from pathlib import Path

# Which dependency files we understand, and which OSV ecosystem each maps to.
MANIFESTS = {
    "requirements.txt": "PyPI",
    "requirements-dev.txt": "PyPI",
    "pyproject.toml": "PyPI",
    "package.json": "npm",
    "package-lock.json": "npm",
    "go.mod": "Go",
    "Cargo.toml": "crates.io",
    "Gemfile.lock": "RubyGems",
}

SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv", "dist", "build", ".next"}
MAX_FILES = 200

# name==1.2.3 / name>=1.2.3 / name[extra]==1.2.3, ignoring markers and comments.
_PY_PIN = re.compile(r"^\s*([A-Za-z0-9._-]+)\s*(?:\[[^\]]*\])?\s*==\s*([A-Za-z0-9._+-]+)")
_GO_REQUIRE = re.compile(r"^\s*([\w./-]+)\s+v([\w.+-]+)")


def find_manifests(root: Path) -> list[Path]:
    found: list[Path] = []
    for path in sorted(root.rglob("*")):
        if len(found) >= MAX_FILES:
            break
        if any(part in SKIP_DIRS for part in path.relative_to(root).parts):
            continue
        if path.is_file() and path.name in MANIFESTS:
            found.append(path)
    return found


def parse(path: Path) -> list[dict]:
    """Extract {name, version, ecosystem} from one manifest.

    Only *pinned* versions are returned. A range like ">=2.0" cannot be checked against a
    vulnerability database - reporting on a version the project may not actually install
    would produce findings nobody can act on.
    """
    ecosystem = MANIFESTS.get(path.name)
    if not ecosystem:
        return []
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []

    if path.name == "package-lock.json":
        return _npm_lock(text)
    if path.name == "package.json":
        return _npm_manifest(text)
    if path.name == "go.mod":
        return _go_mod(text)
    if path.name in {"requirements.txt", "requirements-dev.txt"}:
        return _requirements(text)
    if path.name == "pyproject.toml":
        return _requirements(text)
    return []


def _requirements(text: str) -> list[dict]:
    out = []
    for line in text.splitlines():
        line = line.split("#", 1)[0]
        match = _PY_PIN.match(line)
        if match:
            out.append({"name": match.group(1), "version": match.group(2), "ecosystem": "PyPI"})
    return out


def _npm_manifest(text: str) -> list[dict]:
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return []
    out = []
    for section in ("dependencies", "devDependencies"):
        for name, spec in (data.get(section) or {}).items():
            if isinstance(spec, str) and re.fullmatch(r"\d+\.\d+\.\d+", spec.strip()):
                out.append({"name": name, "version": spec.strip(), "ecosystem": "npm"})
    return out


def _npm_lock(text: str) -> list[dict]:
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return []
    out = []
    # Lockfile v2/v3 keeps everything under "packages" keyed by install path.
    for key, meta in (data.get("packages") or {}).items():
        if not key or not isinstance(meta, dict) or not meta.get("version"):
            continue
        name = key.split("node_modules/")[-1]
        if name:
            out.append({"name": name, "version": meta["version"], "ecosystem": "npm"})
    for name, meta in (data.get("dependencies") or {}).items():
        if isinstance(meta, dict) and meta.get("version"):
            out.append({"name": name, "version": meta["version"], "ecosystem": "npm"})
    return out


def _go_mod(text: str) -> list[dict]:
    out = []
    in_block = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("require ("):
            in_block = True
            continue
        if in_block and stripped == ")":
            in_block = False
            continue
        candidate = stripped[len("require ") :] if stripped.startswith("require ") else (stripped if in_block else "")
        match = _GO_REQUIRE.match(candidate)
        if match:
            out.append({"name": match.group(1), "version": match.group(2), "ecosystem": "Go"})
    return out


def collect(root: Path) -> tuple[list[dict], list[str]]:
    """All pinned dependencies in a workspace, plus which manifests they came from."""
    packages: list[dict] = []
    seen: set[tuple[str, str, str]] = set()
    sources: list[str] = []

    for path in find_manifests(root):
        parsed = parse(path)
        if parsed:
            sources.append(str(path.relative_to(root)).replace("\\", "/"))
        for pkg in parsed:
            key = (pkg["ecosystem"], pkg["name"], pkg["version"])
            if key not in seen:
                seen.add(key)
                packages.append(pkg)
    return packages, sources
