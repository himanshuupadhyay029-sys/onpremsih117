"""initial schema for users, chats, messages

Revision ID: 001_initial_schema
Revises: 
Create Date: 2026-09-04 03:40:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '001_initial_schema'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. users table
    op.create_table(
        'users',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('email', sa.String(length=255), nullable=False),
        sa.Column('password_hash', sa.String(length=255), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    )
    op.create_index(op.f('ix_users_email'), 'users', ['email'], unique=True)

    # 2. chats table
    op.create_table(
        'chats',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('title', sa.String(length=255), server_default='New Chat', nullable=False),
        sa.Column('chat_type', sa.String(length=50), server_default='general', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    )
    op.create_index(op.f('ix_chats_user_id'), 'chats', ['user_id'], unique=False)

    # 3. messages table
    op.create_table(
        'messages',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('chat_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('chats.id', ondelete='CASCADE'), nullable=False),
        sa.Column('role', sa.String(length=50), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('meta', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    )
    op.create_index(op.f('ix_messages_chat_id'), 'messages', ['chat_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_messages_chat_id'), table_name='messages')
    op.drop_table('messages')
    op.drop_index(op.f('ix_chats_user_id'), table_name='chats')
    op.drop_table('chats')
    op.drop_index(op.f('ix_users_email'), table_name='users')
    op.drop_table('users')
