from __future__ import annotations

import datetime as dt

from sqlalchemy.exc import IntegrityError

from .db import Base, SessionLocal, engine
from .models import User
from .security import hash_password
from .settings import settings


def init_db() -> None:
    Base.metadata.create_all(bind=engine)


def seed_example_user(*, email: str, password: str, role: str) -> bool:
    db = SessionLocal()
    try:
        existing = db.query(User).filter(User.email == email).first()
        if existing:
            return False

        user = User(
            email=email,
            password_hash=hash_password(password),
            role=role,
            email_verified_at=dt.datetime.now(dt.timezone.utc),
        )
        db.add(user)
        db.commit()
        return True
    except IntegrityError:
        db.rollback()
        return False
    finally:
        db.close()


def init_db_and_seed_example_user() -> None:
    init_db()

    auto_seed = settings.AUTO_SEED_EXAMPLE_USER
    if auto_seed is None:
        auto_seed = settings.APP_ENV.lower() in {"dev", "local"}
    if not auto_seed:
        return

    email = settings.EXAMPLE_USER_EMAIL.strip().lower()
    created = seed_example_user(
        email=email,
        password=settings.EXAMPLE_USER_PASSWORD,
        role=settings.EXAMPLE_USER_ROLE,
    )
    if created:
        print(f"[seed] Created example user: {email} (role={settings.EXAMPLE_USER_ROLE})")
