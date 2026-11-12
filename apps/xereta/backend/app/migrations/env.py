from alembic import context
from sqlmodel import SQLModel
from app import models

def run():
    connection = context.config.attributes["connection"]
    context.configure(connection=connection, target_metadata=SQLModel.metadata, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()
run()
