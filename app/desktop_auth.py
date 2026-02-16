from __future__ import annotations

import base64
import hashlib
import secrets
import time
from dataclasses import dataclass
from typing import Dict, Optional


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def pkce_challenge_from_verifier(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode("utf-8")).digest()
    return _b64url(digest)


@dataclass
class PendingLogin:
    state: str
    redirect_uri: str
    code_challenge: str
    created_at: float


@dataclass
class AuthCode:
    code: str
    user_id: int
    state: str
    code_challenge: str
    created_at: float
    used: bool = False


class DesktopAuthStore:
    """In-memory store for demo purposes (V1).

    In production, store pending logins and auth codes in DB/redis with TTL.
    """

    def __init__(self, pending_ttl_s: int = 600, code_ttl_s: int = 120):
        self.pending_ttl_s = pending_ttl_s
        self.code_ttl_s = code_ttl_s
        self.pending: Dict[str, PendingLogin] = {}
        self.codes: Dict[str, AuthCode] = {}

    def cleanup(self) -> None:
        now = time.time()
        self.pending = {k: v for k, v in self.pending.items() if now - v.created_at < self.pending_ttl_s}
        self.codes = {k: v for k, v in self.codes.items() if now - v.created_at < self.code_ttl_s and not v.used}

    def register_pending(self, state: str, redirect_uri: str, code_challenge: str) -> None:
        self.cleanup()
        self.pending[state] = PendingLogin(state=state, redirect_uri=redirect_uri, code_challenge=code_challenge, created_at=time.time())

    def get_pending(self, state: str) -> Optional[PendingLogin]:
        self.cleanup()
        return self.pending.get(state)

    def issue_code(self, state: str, user_id: int) -> AuthCode:
        self.cleanup()
        pending = self.pending.get(state)
        if not pending:
            raise ValueError("unknown_state")
        code = secrets.token_urlsafe(24)
        auth_code = AuthCode(code=code, user_id=user_id, state=state, code_challenge=pending.code_challenge, created_at=time.time())
        self.codes[code] = auth_code
        return auth_code

    def exchange_code(self, code: str, code_verifier: str) -> int:
        self.cleanup()
        auth_code = self.codes.get(code)
        if not auth_code or auth_code.used:
            raise ValueError("invalid_code")
        # Verify PKCE
        expected = auth_code.code_challenge
        actual = pkce_challenge_from_verifier(code_verifier)
        if actual != expected:
            raise ValueError("pkce_failed")
        # Mark used
        auth_code.used = True
        return auth_code.user_id


store = DesktopAuthStore()
