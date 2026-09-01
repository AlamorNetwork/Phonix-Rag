import hashlib
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

from app.core.logging import mask_secrets


class EvidenceType:
    SOURCE = "source"                  # a span of a file in the workspace
    DEPENDENCY = "dependency"          # a package at a version, and what is known about it
    COMMAND = "command"                # something run in the sandbox, and its output
    CONFIG = "config"                  # a setting read from a config file
    HTTP = "http"                      # a request/response observed against a running app
    ABSENCE = "absence"                # something expected was looked for and not found
    HUMAN = "human"                    # a person asserted this


@dataclass
class Evidence:
    """One observation supporting an assessment.

    Typed rather than a paragraph of prose so that a later run can compare observations, a
    human can see precisely what was looked at, and nothing rests on an agent's summary of
    what it claims to have seen.
    """

    type: str
    summary: str
    source: str = ""
    observations: dict[str, Any] = field(default_factory=dict)
    content_hash: str | None = None
    observed_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        # Evidence is written to the database and shown in the UI, so it passes the same
        # masking every other stored text does. A config file is exactly where a key lives.
        data = asdict(self)
        data["summary"] = mask_secrets(data["summary"])
        data["source"] = mask_secrets(data["source"])
        data["observations"] = {
            k: mask_secrets(v) if isinstance(v, str) else v for k, v in data["observations"].items()
        }
        return data


def digest(content: str) -> str:
    """Identifies what was observed without storing it. Lets a later run tell whether the
    thing it looked at changed, while keeping file contents out of the finding record."""
    return hashlib.sha256(content.encode("utf-8", errors="replace")).hexdigest()[:16]


def from_source(path: str, line: int | None, excerpt: str, summary: str) -> Evidence:
    return Evidence(
        type=EvidenceType.SOURCE,
        summary=summary,
        source=f"{path}:{line}" if line else path,
        observations={"excerpt": excerpt[:400]},
        content_hash=digest(excerpt),
    )


def from_dependency(package: str, version: str, advisory: str, details: dict) -> Evidence:
    return Evidence(
        type=EvidenceType.DEPENDENCY,
        summary=f"{package} {version} is affected by {advisory}",
        source=f"{package}=={version}",
        observations={"advisory": advisory, **details},
    )


def from_command(args: list[str], returncode: int, stdout: str, stderr: str) -> Evidence:
    combined = f"{stdout}\n{stderr}"
    return Evidence(
        type=EvidenceType.COMMAND,
        summary=f"`{' '.join(args)}` exited {returncode}",
        source=" ".join(args),
        observations={"returncode": returncode, "output": combined[:1000]},
        content_hash=digest(combined),
    )


def from_absence(looked_for: str, searched: str) -> Evidence:
    """Recording that something was looked for and not found is different from not having
    looked - which is the whole reason UNKNOWN exists as a result."""
    return Evidence(
        type=EvidenceType.ABSENCE,
        summary=f"{looked_for} was not found",
        source=searched,
        observations={"looked_for": looked_for, "searched": searched},
    )
