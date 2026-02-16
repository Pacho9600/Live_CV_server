from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from .api.auth import router as auth_router
from .api.desktop_login import router as desktop_login_router
from .bootstrap import init_db_and_seed_example_user


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db_and_seed_example_user()
    yield

app = FastAPI(title="Architecture Showcase API", version="0.2.0", lifespan=lifespan)

app.include_router(auth_router)
app.include_router(desktop_login_router)

@app.get("/health")
def health():
    return {"status": "ok"}
