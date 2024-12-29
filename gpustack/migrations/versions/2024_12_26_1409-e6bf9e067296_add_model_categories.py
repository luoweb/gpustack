"""add model categories

Revision ID: e6bf9e067296
Revises: 004c73a5c09e
Create Date: 2024-12-26 14:09:59.306468

"""
import json
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel
import gpustack


# revision identifiers, used by Alembic.
revision: str = 'e6bf9e067296'
down_revision: Union[str, None] = '004c73a5c09e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('models', schema=None) as batch_op:
        batch_op.add_column(sa.Column('categories', sa.JSON(), nullable=True))
        batch_op.add_column(sa.Column('meta', sa.JSON(), nullable=True, default={}))

    with op.batch_alter_table('model_instances', schema=None) as batch_op:
        batch_op.alter_column('state',
                      existing_type=sa.VARCHAR(length=16),
                      type_=sa.Enum('INITIALIZING', 'PENDING', 'STARTING', 'RUNNING', 'SCHEDULED', 'ERROR', 'DOWNLOADING', 'ANALYZING', name='modelinstancestateenum'),
                      existing_nullable=False)

    with op.batch_alter_table('models', schema=None) as batch_op:
        connection = batch_op.get_bind()
        categories_case = sa.case(
                (sa.column('reranker') == True, sa.literal(json.dumps(['reranker']))),
                (sa.column('embedding_only') == True, sa.literal(json.dumps(['embedding']))),
                (sa.column('image_only') == True, sa.literal(json.dumps(['image']))),
                (sa.column('speech_to_text') == True, sa.literal(json.dumps(['speech_to_text']))),
                (sa.column('text_to_speech') == True, sa.literal(json.dumps(['text_to_speech']))),
                else_=sa.literal(json.dumps([]))
            )
        if connection.dialect.name == 'postgresql':
            categories_case = sa.case(
                (sa.column('reranker') == True, sa.func.to_json(['reranker'])),
                (sa.column('embedding_only') == True, sa.func.to_json(['embedding'])),
                (sa.column('image_only') == True, sa.func.to_json(['image'])),
                (sa.column('speech_to_text') == True, sa.func.to_json(['speech_to_text'])),
                (sa.column('text_to_speech') == True, sa.func.to_json(['text_to_speech'])),
                else_=sa.literal([])
            )

        models_table = sa.table('models', sa.column('categories', sa.JSON))
        connection.execute(
            sa.update(models_table).values(
                categories=categories_case
            )
        )


def downgrade() -> None:
    with op.batch_alter_table('models', schema=None) as batch_op:
        batch_op.drop_column('categories')
        batch_op.drop_column('meta')

    with op.batch_alter_table('model_instances', schema=None) as batch_op:
        batch_op.alter_column('state',
                      existing_type=sa.VARCHAR(length=16),
                      type_=sa.Enum('INITIALIZING', 'PENDING', 'RUNNING', 'SCHEDULED', 'ERROR', 'DOWNLOADING', 'ANALYZING', name='modelinstancestateenum'),
                      existing_nullable=False)
