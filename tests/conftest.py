import os
from pathlib import Path
import sys
import pytest
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / '.env')
os.environ['APP_ENV'] = 'development'
os.environ['RESET_MODE'] = 'demo'
os.environ['DEMO_SEED_ENABLED'] = 'true'


@pytest.fixture(scope='session')
def test_engine():
    # Explicit separate database only: never create/drop tables in the app database.
    if os.getenv('SUPPORTDESK_TEST_DB') != 'supportdesk_test':
        pytest.skip('Set SUPPORTDESK_TEST_DB=supportdesk_test and create that isolated PostgreSQL database.')
    from app.config import settings
    from app.models import Base
    url = settings().database_url.set(database='supportdesk_test')
    value = create_engine(url, pool_pre_ping=True)
    Base.metadata.create_all(value)
    yield value
    value.dispose()


@pytest.fixture
def db(test_engine):
    from database.seed import seed
    connection = test_engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection, join_transaction_mode='create_savepoint', expire_on_commit=False)
    seed(session)
    yield session
    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture
def client(db):
    from app.main import app
    from app.db import get_db
    app.dependency_overrides[get_db] = lambda: db
    with TestClient(app, base_url='http://localhost:5173') as value:
        yield value
    app.dependency_overrides.clear()


def login(client, admin=False):
    from app.config import settings
    cfg = settings()
    r = client.post('/api/auth/login', json={'email': cfg.demo_admin_email if admin else cfg.demo_user_email, 'password': cfg.demo_password})
    assert r.status_code == 200, r.text
    client.headers['X-CSRF-Token'] = client.cookies['sd_csrf']
    return r.json()
