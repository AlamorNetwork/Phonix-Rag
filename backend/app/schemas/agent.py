from datetime import datetime

from pydantic import BaseModel


class AgentRunRequest(BaseModel):
    message: str


class AgentModelUpdate(BaseModel):
    model_id: str


class AgentResponse(BaseModel):
    id: str
    project_id: str
    role: str
    allowed_tools: list[str]
    allowed_models: list[str]
    selected_model_id: str | None
    budget_usd: float
    max_iterations: int
    summary: str = ""

    class Config:
        from_attributes = True
        protected_namespaces = ()


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
