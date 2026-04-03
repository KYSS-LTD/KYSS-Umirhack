from pydantic import BaseModel, Field


class TaskCreateRequest(BaseModel):
    task_uid: str = Field(min_length=8, max_length=64)
    task_type: str
    command: str | None = None
    agent_uid: str | None = None


class TaskOut(BaseModel):
    task_uid: str
    task_type: str
    command: str | None
    status: str
    result: str | None

    class Config:
        from_attributes = True
