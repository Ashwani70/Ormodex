"""Reset the admin password directly against Supabase PostgreSQL.

Usage:
    cd backend
    ADMIN_EMAIL=admin@example.com ADMIN_PASSWORD=NewPass123 python update_admin_pwd.py

No MongoDB dependency — uses the same SQLAlchemy async session as the app.
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from dotenv import load_dotenv
load_dotenv(".env")

from sqlalchemy import select
from core.db import get_session
from core.schema import User
from core.auth_utils import hash_password
from core.utils import new_id, now_iso


async def main() -> None:
    admin_email = os.environ.get("ADMIN_EMAIL", "admin@example.com").lower()
    admin_password = os.environ.get("ADMIN_PASSWORD", "Admin@123456")

    print(f"Connecting to PostgreSQL (Supabase)…")
    async with get_session() as session:
        result = await session.execute(select(User).where(User.email == admin_email))
        existing = result.scalars().first()

        pwd_hash = hash_password(admin_password)

        if existing:
            existing.password_hash = pwd_hash
            existing.updated_at = now_iso()
            print(f"Updated password for existing admin: {admin_email}")
        else:
            user = User(
                id=new_id(),
                name="Administrator",
                email=admin_email,
                phone="+91 9876543210",
                role="admin",
                password_hash=pwd_hash,
                is_active=True,
                created_at=now_iso(),
                updated_at=now_iso(),
            )
            session.add(user)
            print(f"Created new admin user: {admin_email}")

    print("Done.")


if __name__ == "__main__":
    asyncio.run(main())
