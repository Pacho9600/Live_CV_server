from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import User
from ..schemas import DesktopExchangeRequest, TokenResponse, MeResponse
from ..security import create_access_token
from ..auth_deps import require_user
from ..desktop_auth import store

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/desktop/exchange", response_model=TokenResponse)
def desktop_exchange(data: DesktopExchangeRequest, db: Session = Depends(get_db)) -> TokenResponse:
    """Exchange one-time auth code + PKCE verifier for a JWT access token."""
    try:
        user_id = store.exchange_code(code=data.code, code_verifier=data.code_verifier)
    except ValueError as e:
        msg = str(e)
        if msg == "pkce_failed":
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="PKCE verification failed")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired auth code")

    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unknown user")

    token = create_access_token(subject=str(user.id), extra={"email": user.email, "role": user.role})
    return TokenResponse(access_token=token)


@router.get("/me", response_model=MeResponse)
def me(payload: dict = Depends(require_user), db: Session = Depends(get_db)) -> MeResponse:
    user_id = int(payload["sub"])
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unknown user")

    return MeResponse(
        id=user.id,
        email=user.email,
        role=user.role,
        email_verified=bool(user.email_verified_at),
    )
