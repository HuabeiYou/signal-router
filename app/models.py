from datetime import datetime
from typing import Optional

from sqlmodel import Field, SQLModel


class Signal(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    received_at: datetime = Field(default_factory=datetime.utcnow, nullable=False)
    source: Optional[str] = Field(default=None, max_length=100)
    raw_payload: str = Field(nullable=False)
    parsed_fields: str = Field(nullable=False)
    match_count: int = Field(default=0, nullable=False)
    delivery_count: int = Field(default=0, nullable=False)


class Rule(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(unique=True, index=True, max_length=100, nullable=False)
    enabled: bool = Field(default=True, nullable=False)
    priority: int = Field(default=0, nullable=False)
    conditions_json: str = Field(nullable=False)
    action_json: str = Field(nullable=False)
    created_at: datetime = Field(default_factory=datetime.utcnow, nullable=False)
    updated_at: datetime = Field(default_factory=datetime.utcnow, nullable=False)


class Delivery(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    signal_id: int = Field(foreign_key="signal.id", nullable=False, index=True)
    rule_id: int = Field(foreign_key="rule.id", nullable=False, index=True)
    target_masked: str = Field(max_length=255, nullable=False)
    target_encrypted: str = Field(nullable=False)
    request_payload: str = Field(nullable=False)
    response_status: Optional[int] = Field(default=None)
    response_body: Optional[str] = Field(default=None)
    success: bool = Field(nullable=False)
    error_message: Optional[str] = Field(default=None)
    created_at: datetime = Field(default_factory=datetime.utcnow, nullable=False, index=True)
