"""Provider identities and non-destructive copy relationships."""
from alembic import op
import sqlalchemy as sa

revision = '0004'
down_revision = '0003'


def upgrade():
    for name, default in [('provider', 'silverbullet'), ('connection_id', 'silverbullet'),
                          ('external_id', ''), ('permalink', ''), ('family_id', '')]:
        op.add_column('source', sa.Column(name, sa.String(), nullable=False, server_default=default))
    op.execute(sa.text("UPDATE source SET family_id=id, external_id=path"))
    op.execute(sa.text("UPDATE source SET provider='feedback',connection_id='feedback' WHERE path LIKE 'feedback:%'"))
    op.add_column('version', sa.Column('title', sa.String(), nullable=False, server_default=''))
    op.execute(sa.text("UPDATE version SET title=(SELECT CASE WHEN source.path LIKE 'feedback:%' THEN 'Resposta do proprietário' ELSE source.title END FROM source WHERE source.id=version.source_id) WHERE EXISTS (SELECT 1 FROM source WHERE source.id=version.source_id)"))
    op.add_column('intakesection', sa.Column('reused_from', sa.String(), nullable=False, server_default=''))
    op.create_table('sourceconnection', sa.Column('id', sa.String(), primary_key=True),
        sa.Column('provider', sa.String(), nullable=False), sa.Column('workspace', sa.String(), nullable=False),
        sa.Column('exclusions', sa.JSON()), sa.Column('approved_at', sa.String(), nullable=False),
        sa.Column('paused', sa.Boolean(), nullable=False), sa.Column('revision', sa.Integer(), nullable=False))
    op.create_table('sourcerelationship', sa.Column('id', sa.String(), primary_key=True),
        sa.Column('source_id', sa.String(), nullable=False), sa.Column('target_id', sa.String(), nullable=False),
        sa.Column('state', sa.String(), nullable=False), sa.Column('method', sa.String(), nullable=False),
        sa.Column('revision', sa.Integer(), nullable=False), sa.UniqueConstraint('source_id', 'target_id'))


def downgrade():
    raise RuntimeError('Restore a verified backup; never delete source or relationship history')
