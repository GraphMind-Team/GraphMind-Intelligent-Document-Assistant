from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from dotenv import load_dotenv
import os

load_dotenv()

class Base(DeclarativeBase):
    pass

engine = create_async_engine(os.getenv("DATABASE_URL"), 
                             echo=True, 
                             connect_args={"statement_cache_size": 0})


session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

async def get_db():
    async with session() as db:
        yield db
