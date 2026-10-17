from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base, get_db
from app.main import app, settings
from app.seed.seed import ensure_portfolio_extension, seed_database


@pytest.fixture()
def test_context(tmp_path: Path):
    # Automated acceptance tests must be deterministic and must not consume
    # external provider quota merely because a developer has local keys.
    old_provider_keys = (settings.groq_api_key, settings.gemini_api_key, settings.jev_api_key)
    settings.groq_api_key = None
    settings.gemini_api_key = None
    settings.jev_api_key = None
    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}", connect_args={"check_same_thread": False})
    TestingSession = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    Base.metadata.create_all(engine)
    with TestingSession() as db:
        seed_database(db)
        ensure_portfolio_extension(db)

    def override_db():
        db = TestingSession()
        try:
            yield db
        finally:
            db.close()

    old_upload = settings.upload_dir
    settings.upload_dir = tmp_path / "uploads"
    app.dependency_overrides[get_db] = override_db
    with TestClient(app) as client:
        yield client, TestingSession, tmp_path
    app.dependency_overrides.clear()
    settings.upload_dir = old_upload
    settings.groq_api_key, settings.gemini_api_key, settings.jev_api_key = old_provider_keys
