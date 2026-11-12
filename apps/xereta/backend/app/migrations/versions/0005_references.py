"""Reference catalogue is separate from the knowledge retention tables."""
from alembic import op
import sqlalchemy as sa

revision = '0005'
down_revision = '0004'


def upgrade():
    op.create_table('referenceitem', sa.Column('id', sa.String(), primary_key=True),
        sa.Column('url', sa.String(), nullable=False),
        *[sa.Column(k, sa.String(), nullable=False) for k in ('title','description','context','kind')],
        *[sa.Column(k, sa.JSON()) for k in ('tags','suggested_tags','projects')],
        *[sa.Column(k, sa.String(), nullable=False) for k in ('bookmark_id','candidate_hash','approved_hash','approval_origin')],
        sa.Column('revision', sa.Integer(), nullable=False),
        *[sa.Column(k, sa.String(), nullable=False) for k in ('state','error','organized_hash','updated_at')])
    op.create_index('ix_referenceitem_url','referenceitem',['url'],unique=True)
    op.create_table('referencemention', sa.Column('id', sa.String(), primary_key=True),
        *[sa.Column(k, sa.String(), nullable=False) for k in ('reference_id','path','version','title')],
        sa.Column('start', sa.Integer(), nullable=False), sa.Column('end', sa.Integer(), nullable=False),
        sa.Column('context', sa.String(), nullable=False), sa.Column('tags', sa.JSON()), sa.Column('active', sa.Boolean(), nullable=False))
    op.create_index('ix_referencemention_reference_id','referencemention',['reference_id'])
    op.create_table('referencecapture', sa.Column('id', sa.String(), primary_key=True),
        *[sa.Column(k, sa.String(), nullable=False) for k in ('reference_id','hash','body_hash','title','body','article_body','annotations','final_url','captured_at')],
        sa.UniqueConstraint('reference_id','hash'))
    op.create_index('ix_referencecapture_reference_id','referencecapture',['reference_id'])
    op.create_table('knowledgerelation', sa.Column('id', sa.String(), primary_key=True),
        *[sa.Column(k, sa.String(), nullable=False) for k in ('source_id','target_id','kind','origin','state','reason')],
        sa.Column('evidence', sa.JSON()), sa.Column('revision', sa.Integer(), nullable=False))
    for column in ('source_id','target_id'):
        op.create_index('ix_knowledgerelation_'+column,'knowledgerelation',[column])


def downgrade():
    raise RuntimeError('Restore a verified backup; retain reference approvals and provenance')
