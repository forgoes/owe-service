from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.runtime.config import settings


engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
    echo=settings.db_echo,
)

SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
)

_database_initialized = False


def initialize_database() -> None:
    global _database_initialized
    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))
    _database_initialized = True


def is_database_initialized() -> bool:
    return _database_initialized
