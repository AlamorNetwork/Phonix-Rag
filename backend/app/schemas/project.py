from datetime import datetime

from pydantic import BaseModel


class ProjectCreate(BaseModel):
    name: str
    idea: str


class ProjectResponse(BaseModel):
    id: str
    name: str
    idea: str
    status: str
    created_at: datetime

    class Config:
        from_attributes = True
