from datetime import datetime

from pydantic import BaseModel


class AgentRunRequest(BaseModel):
    message: str


class AgentRunResponse(BaseModel):
    id: str
    agent_id: str
    project_id: str
    status: str
    input_message: str
    output_message: str | None
    created_at: datetime

    class Config:
        from_attributes = True
