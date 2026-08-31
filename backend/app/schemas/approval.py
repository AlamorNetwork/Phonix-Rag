from datetime import datetime

from pydantic import BaseModel


class ApprovalResponse(BaseModel):
    id: str
    tool_execution_id: str
    agent_run_id: str
    risk_level: str
    reason: str
    status: str
    decided_by: str | None
    decided_at: datetime | None
    created_at: datetime

    class Config:
        from_attributes = True


class ApprovalDecisionRequest(BaseModel):
    reason: str | None = None
