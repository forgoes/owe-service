from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase

from app.runtime.config import settings


class Base(DeclarativeBase):
    metadata = MetaData(schema=settings.db_schema)
