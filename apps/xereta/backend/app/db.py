from contextlib import contextmanager

from sqlalchemy import text
from sqlmodel import Session, SQLModel, create_engine, select

from app.models import Publication, Schedule, User
from app.security import get_password_hash


def make_engine(url):
    kwargs = {"connect_args": {"check_same_thread": False}} if url.startswith("sqlite:") else {"pool_pre_ping": True}
    return create_engine(url, **kwargs)


def initialize(engine, settings):
    from pathlib import Path
    from alembic import command
    from alembic.config import Config
    from sqlalchemy import inspect
    from alembic.autogenerate import compare_metadata
    from alembic.migration import MigrationContext
    cfg = Config()
    cfg.set_main_option("script_location", str(Path(__file__).with_name("migrations")))
    with engine.begin() as connection:
        if engine.dialect.name == "postgresql":
            connection.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": 1481855591})
        cfg.attributes["connection"] = connection
        tables = set(inspect(connection).get_table_names())
        if tables and "alembic_version" not in tables:
            # Adopt only the exact pre-migration pilot schema. Unknown schemas fail closed.
            if compare_metadata(MigrationContext.configure(connection), SQLModel.metadata):
                raise RuntimeError("legacy_schema_requires_explicit_migration")
            command.stamp(cfg, "0001")
        command.upgrade(cfg, "head")
    with Session(engine) as s:
        if not s.exec(select(User)).first():
            s.add(User(email=settings.owner_email,
                       password_hash=get_password_hash(settings.owner_password.get_secret_value())))
        if not s.get(Schedule, 1):
            s.add(Schedule())
        if not s.get(Publication, 1):
            s.add(Publication())
        s.commit()


@contextmanager
def worker_lock(engine):
    """Keep the PostgreSQL advisory-lock connection checked out for the whole run."""
    with engine.connect() as connection:
        locked = engine.dialect.name != "postgresql" or connection.execute(
            text("SELECT pg_try_advisory_lock(:key)"), {"key": 1481855589}).scalar()
        try:
            yield bool(locked)
        finally:
            if locked and engine.dialect.name == "postgresql":
                connection.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": 1481855589})
