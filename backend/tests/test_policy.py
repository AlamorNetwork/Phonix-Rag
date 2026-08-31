from app.policies.risk import PolicyEngine, RiskLevel


def test_read_is_auto_approved_by_default():
    engine = PolicyEngine()
    assert engine.requires_approval(RiskLevel.READ) is False


def test_low_and_above_require_approval_by_default():
    engine = PolicyEngine()
    assert engine.requires_approval(RiskLevel.LOW) is True
    assert engine.requires_approval(RiskLevel.MEDIUM) is True
    assert engine.requires_approval(RiskLevel.HIGH) is True
    assert engine.requires_approval(RiskLevel.CRITICAL) is True


def test_threshold_is_configurable():
    engine = PolicyEngine(auto_approve_max_risk=RiskLevel.LOW)
    assert engine.requires_approval(RiskLevel.LOW) is False
    assert engine.requires_approval(RiskLevel.MEDIUM) is True


def test_risk_level_from_str():
    assert RiskLevel.from_str("medium") is RiskLevel.MEDIUM
    assert RiskLevel.from_str("CRITICAL") is RiskLevel.CRITICAL
