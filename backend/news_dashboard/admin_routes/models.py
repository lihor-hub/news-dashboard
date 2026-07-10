"""Request models for the admin routes domain."""

from __future__ import annotations

from pydantic import BaseModel


class CreateUserRequest(BaseModel):
    username: str
    password: str
    email: str | None = None
    is_admin: bool = False


class UpdatePasswordRequest(BaseModel):
    password: str


class GenerateUserRequest(BaseModel):
    username: str
    email: str | None = None
    is_admin: bool = False
