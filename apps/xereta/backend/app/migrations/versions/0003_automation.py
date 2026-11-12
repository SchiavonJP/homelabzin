"""Durable scoped intake, section checkpoints and shared daily budgets."""
from alembic import op
import sqlalchemy as sa

revision = '0003'
down_revision = '0002'


def upgrade():
    op.create_table('automationpolicy',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('revision', sa.Integer(), nullable=False),
        sa.Column('mode', sa.String(), nullable=False),
        sa.Column('paused', sa.Boolean(), nullable=False),
        sa.Column('folders', sa.JSON()), sa.Column('exclusions', sa.JSON()),
        sa.Column('notes_per_day', sa.Integer(), nullable=False),
        sa.Column('minutes_per_day', sa.Integer(), nullable=False),
        sa.Column('approved_at', sa.String(), nullable=False))
    op.create_table('intakenote',
        sa.Column('path', sa.String(), primary_key=True),
        sa.Column('source_id', sa.String(), nullable=False), sa.Column('version', sa.String(), nullable=False),
        sa.Column('state', sa.String(), nullable=False), sa.Column('inventory', sa.JSON()),
        sa.Column('verified_at', sa.String(), nullable=False), sa.Column('discovered_at', sa.String(), nullable=False),
        sa.Column('worked_at', sa.String(), nullable=False), sa.Column('attempts', sa.Integer(), nullable=False),
        sa.Column('next_attempt_at', sa.String(), nullable=False), sa.Column('error', sa.String(), nullable=False))
    op.create_table('intakesection',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('source_id', sa.String(), nullable=False), sa.Column('version', sa.String(), nullable=False),
        sa.Column('number', sa.Integer(), nullable=False), sa.Column('start', sa.Integer(), nullable=False),
        sa.Column('end', sa.Integer(), nullable=False), sa.Column('kind', sa.String(), nullable=False),
        sa.Column('document_id', sa.String(), nullable=False),
        sa.Column('state', sa.String(), nullable=False), sa.Column('operation_id', sa.String(), nullable=False),
        sa.Column('error', sa.String(), nullable=False), sa.Column('attempts', sa.Integer(), nullable=False),
        sa.Column('next_attempt_at', sa.String(), nullable=False),
        sa.UniqueConstraint('source_id', 'version', 'number'))
    op.create_index('ix_intakesection_source_id', 'intakesection', ['source_id'])
    op.create_table('automationrun',
        sa.Column('run_id', sa.String(), primary_key=True), sa.Column('policy', sa.JSON()),
        sa.Column('day', sa.String(), nullable=False), sa.Column('limit_seconds', sa.Float(), nullable=False),
        sa.Column('charged_seconds', sa.Float(), nullable=False), sa.Column('accounted', sa.Boolean(), nullable=False))
    op.create_table('dailyusage', sa.Column('day', sa.String(), primary_key=True),
        sa.Column('seconds', sa.Float(), nullable=False), sa.Column('notes', sa.JSON()))


def downgrade():
    raise RuntimeError('Restore a verified backup rather than deleting automatic processing history')
