from pydantic import BaseModel, Field


class AgentRegisterRequest(BaseModel):
    agent_uid: str = Field(min_length=4, max_length=64)
    hostname: str = Field(min_length=1, max_length=255)
    public_key: str = ''
    registration_token: str


class SignedEnvelope(BaseModel):
    agent_uid: str
    timestamp: int | None = None
    payload: dict
    signature: str | None = None
    nonce: str | None = None


class TaskResultPayload(BaseModel):
    task_uid: str
    status: str
    result: str
    logs: str | None = None
