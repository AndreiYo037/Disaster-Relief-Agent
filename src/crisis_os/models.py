from __future__ import annotations
from typing import Literal
from pydantic import BaseModel, Field


class HumanDecision(BaseModel):
    actor: str
    role: str
    action: Literal["approve", "modify", "reject"]
    reason: str
    modifications: dict = Field(default_factory=dict)


class Permit(BaseModel):
    permit_id: str
    plan_id: str
    status: str
    authorized_actions: list[str]
    approved_by: str
    authorized_route: str
