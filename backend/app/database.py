from collections.abc import Generator

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import get_settings


class Base(DeclarativeBase):
    pass


settings = get_settings()
connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
engine = create_engine(settings.database_url, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    from . import models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    _apply_compatible_schema_extensions()


def _apply_compatible_schema_extensions() -> None:
    """Small SQLite migration bridge for the hackathon database.

    The project intentionally has no migration history yet. These additive,
    nullable/defaulted columns keep existing local data while allowing the
    richer floor-plan workspace to start against an older local database.
    """
    if engine.dialect.name != "sqlite":
        return
    additions = {
        "floor_plans": {
            "name": "VARCHAR(160) NOT NULL DEFAULT 'Original plan'",
            "plan_type": "VARCHAR(40) NOT NULL DEFAULT 'base'",
            "is_base": "BOOLEAN NOT NULL DEFAULT 0",
            "source_group": "VARCHAR(80)",
            "analysis_status": "VARCHAR(40) NOT NULL DEFAULT 'not_requested'",
            "analysis_model": "VARCHAR(100)",
            "analyzed_at": "DATETIME",
            "analysis_summary": "JSON NOT NULL DEFAULT '{}'",
        },
        "floor_objects": {
            "details": "JSON NOT NULL DEFAULT '{}'",
            "source_mode": "VARCHAR(40) NOT NULL DEFAULT 'human'",
            "analysis_model": "VARCHAR(100)",
            "confidence_label": "VARCHAR(20)",
            "created_at": "DATETIME",
        },
    }
    with engine.begin() as connection:
        inspector = inspect(connection)
        for table_name, columns in additions.items():
            if table_name not in inspector.get_table_names():
                continue
            existing = {column["name"] for column in inspector.get_columns(table_name)}
            for column_name, ddl in columns.items():
                if column_name not in existing:
                    connection.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {ddl}"))
