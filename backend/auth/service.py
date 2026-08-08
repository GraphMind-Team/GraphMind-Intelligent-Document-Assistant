from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from auth.security import hash_password
from auth.schemas import UserCreate
from auth.models import User


class EmailAlreadyExistsError(Exception):
    pass


async def create_user(db: AsyncSession, user: UserCreate) -> User:
    existing = await db.scalar(select(User).where(User.email == user.email))
    if existing is not None:
        raise EmailAlreadyExistsError(user.email)

    db_user = User(email=user.email, password_hash=hash_password(user.password))

    db.add(db_user)
    await db.commit()
    await db.refresh(db_user)

    return db_user
