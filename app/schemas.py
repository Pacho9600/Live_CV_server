from __future__ import annotations

from pydantic import BaseModel, EmailStr


class DesktopExchangeRequest(BaseModel):
    code: str
    code_verifier: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class MeResponse(BaseModel):
    id: int
    email: EmailStr
    role: str
    email_verified: bool
