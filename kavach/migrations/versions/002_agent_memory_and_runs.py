"""agent memory on chats and agent_runs table for pause/resume

Revision ID: 002_agent_memory_and_runs
Revises: 001_initial_schema
Create Date: 2026-09-08 17:35:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '002_agent_memory_and_runs'
down_revision: Union[str, None] = '001_initial_schema'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Add agent_memory to chats
    op.add_column(
        'chats',
        sa.Column('agent_memory', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False)
    )

    # 2. Create agent_runs table
    op.create_table(
        'agent_runs',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('chat_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('chats.id', ondelete='CASCADE'), nullable=True),
        sa.Column('task_id', sa.String(length=255), nullable=False),
        sa.Column('status', sa.String(length=50), server_default='running', nullable=False),
        sa.Column('state_snapshot', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    )
    op.create_index(op.f('ix_agent_runs_task_id'), 'agent_runs', ['task_id'], unique=True)
    op.create_index(op.f('ix_agent_runs_chat_id'), 'agent_runs', ['chat_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_agent_runs_chat_id'), table_name='agent_runs')
    op.drop_index(op.f('ix_agent_runs_task_id'), table_name='agent_runs')
    op.drop_table('agent_runs')
    op.drop_column('chats', 'agent_memory')
