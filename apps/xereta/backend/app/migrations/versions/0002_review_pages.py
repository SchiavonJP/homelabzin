"""Publish each review item independently without changing existing answers."""
from alembic import op
import sqlalchemy as sa

revision = "0002"
down_revision = "0001"


def upgrade():
    op.create_table("reviewpage",
        sa.Column("path", sa.String(), primary_key=True),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("entity_id", sa.String(), nullable=False),
        sa.Column("body", sa.String(), nullable=False),
        sa.Column("etag", sa.String(), nullable=False),
        sa.Column("pending_body", sa.String(), nullable=False),
        sa.Column("state", sa.String(), nullable=False),
        sa.Column("error", sa.String(), nullable=False),
        sa.Column("published_at", sa.String(), nullable=False))
    op.create_index("ix_reviewpage_entity_id", "reviewpage", ["entity_id"])


def downgrade():
    raise RuntimeError("Restore a verified backup rather than dropping review history")
