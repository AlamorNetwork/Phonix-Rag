from datetime import datetime

from pydantic import BaseModel


class TaskResponse(BaseModel):
    id: str
    project_id: str
    order_index: int
    title: str
    description: str
    assigned_role: str
    status: str
    attempts: int
    estimated_cost_usd: float | None
    agent_run_id: str | None
    review_notes: str | None
    created_at: datetime

    class Config:
        from_attributes = True


class PlanResponse(BaseModel):
    project_id: str
    project_status: str
    tasks: list[TaskResponse]
    estimated_total_usd: float | None
