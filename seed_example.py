from __future__ import annotations

from app.bootstrap import init_db, seed_example_user
from app.settings import settings


def main():
    init_db()

    email = settings.EXAMPLE_USER_EMAIL.strip().lower()
    created = seed_example_user(
        email=email,
        password=settings.EXAMPLE_USER_PASSWORD,
        role=settings.EXAMPLE_USER_ROLE,
    )
    if created:
        print("[seed] Created example user:")
        print(f"       email: {settings.EXAMPLE_USER_EMAIL}")
        print(f"       password: {settings.EXAMPLE_USER_PASSWORD}")
        print(f"       role: {settings.EXAMPLE_USER_ROLE}")
    else:
        print(f"[seed] Example user already exists: {email} (role={settings.EXAMPLE_USER_ROLE})")


if __name__ == "__main__":
    main()
