from enum import IntEnum


class RiskLevel(IntEnum):
    READ = 0
    LOW = 1
    MEDIUM = 2
    HIGH = 3
    CRITICAL = 4

    @classmethod
    def from_str(cls, value: str) -> "RiskLevel":
        return cls[value.upper()]


class PolicyEngine:
    """Decides whether a tool call can be auto-approved or needs a human in the loop.

    Phase 0 policy: anything above READ risk requires approval. This is intentionally the
    only knob for now — per-agent/per-project policy overrides are a later phase.
    """

    def __init__(self, auto_approve_max_risk: RiskLevel = RiskLevel.READ):
        self.auto_approve_max_risk = auto_approve_max_risk

    def requires_approval(self, risk_level: RiskLevel) -> bool:
        return risk_level > self.auto_approve_max_risk


policy_engine = PolicyEngine()
