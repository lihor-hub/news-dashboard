"""Request models for the login/OTP HTTP layer."""

from __future__ import annotations

from pydantic import BaseModel


class LoginRequest(BaseModel):
    username: str
    password: str


class OTPRequestPayload(BaseModel):
    email: str


class OTPLoginPayload(BaseModel):
    email: str
    otp: str
