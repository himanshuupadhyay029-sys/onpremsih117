"""Add role and department to users, create documents and approvals tables

Revision ID: 003_roles_and_classification
Revises: 002_agent_memory_and_runs
Create Date: 2026-09-25 12:50:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '003_roles_and_classification'
down_revision: Union[str, None] = '002_agent_memory_and_runs'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Add role and department to users (additive, with defaults for existing rows)
    op.add_column(
        'users',
        sa.Column('role', sa.String(length=50), server_default='engineer', nullable=False)
    )
    op.add_column(
        'users',
        sa.Column('department', sa.String(length=100), server_default='general', nullable=False)
    )

    # 2. Create documents metadata table (sits alongside FAISS/BM25, keyed by filename)
    op.create_table(
        'documents',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            'owner_user_id',
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey('users.id', ondelete='CASCADE'),
            nullable=False,
        ),
        sa.Column('filename', sa.String(length=500), nullable=False),
        sa.Column('department', sa.String(length=100), server_default='general', nullable=False),
        sa.Column(
            'classification_level',
            sa.String(length=50),
            server_default='internal',
            nullable=False,
        ),
        sa.Column(
            'uploaded_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
    )
    op.create_index(
        'ix_documents_owner_filename',
        'documents',
        ['owner_user_id', 'filename'],
        unique=True,
    )

    # 3. Create approvals table (used by Part B — approval routing)
    op.create_table(
        'approvals',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('task_id', sa.String(length=255), nullable=False),
        sa.Column('department', sa.String(length=100), nullable=True),
        sa.Column('risk_level', sa.String(length=50), nullable=True),
        sa.Column('status', sa.String(length=50), server_default='pending', nullable=False),
        sa.Column(
            'approver_user_id',
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey('users.id'),
            nullable=True,
        ),
        sa.Column(
            'requested_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.Column('decided_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('original_draft', sa.Text(), nullable=True),
        sa.Column('final_draft', sa.Text(), nullable=True),
        sa.Column('diff', sa.Text(), nullable=True),
    )
    op.create_index('ix_approvals_task_id', 'approvals', ['task_id'])


def downgrade() -> None:
    op.drop_index('ix_approvals_task_id', table_name='approvals')
    op.drop_table('approvals')
    op.drop_index('ix_documents_owner_filename', table_name='documents')
    op.drop_table('documents')
    op.drop_column('users', 'department')
    op.drop_column('users', 'role')
