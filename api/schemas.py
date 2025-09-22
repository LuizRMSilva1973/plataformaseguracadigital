from typing import List, Optional, Any
from pydantic import BaseModel, Field


class EventIn(BaseModel):
    ts: str
    host: Optional[str] = None
    app: Optional[str] = None
    event_type: Optional[str] = None
    src_ip: Optional[str] = None
    dst_ip: Optional[str] = None
    username: Optional[str] = None
    severity: Optional[str] = None
    raw: Optional[Any] = None


class IngestBatchIn(BaseModel):
    agent_id: str = Field(..., alias="agent_id")
    batch_id: str
    events: List[EventIn]


class AgentRegisterIn(BaseModel):
    agent_id: str
    os: Optional[str] = None
    version: Optional[str] = None
    host: Optional[str] = None


class ScoreOut(BaseModel):
    score: int
    window_days: int

