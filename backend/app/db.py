from functools import lru_cache
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from .config import settings


@lru_cache
def engine():
    return create_engine(settings().database_url, pool_pre_ping=True, pool_size=4, max_overflow=2,
                         connect_args={'connect_timeout': 5})


def get_db():
    with sessionmaker(engine(), expire_on_commit=False)() as db:
        yield db
