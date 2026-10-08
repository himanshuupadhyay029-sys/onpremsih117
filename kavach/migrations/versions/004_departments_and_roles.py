"""Create departments and roles tables and seed initial defaults

Revision ID: 004_departments_and_roles
Revises: 003_roles_and_classification
Create Date: 2026-09-25 18:45:00.000000

"""
from typing import Sequence, Union
import uuid

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '004_departments_and_roles'
down_revision: Union[str, None] = '003_roles_and_classification'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Create departments table
    departments_table = op.create_table(
        'departments',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('description', sa.String(length=255), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    )
    op.create_index('ix_departments_name', 'departments', ['name'], unique=True)

    # 2. Create roles table
    roles_table = op.create_table(
        'roles',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('name', sa.String(length=50), nullable=False),
        sa.Column('description', sa.String(length=255), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    )
    op.create_index('ix_roles_name', 'roles', ['name'], unique=True)

    # 3. Seed default departments
    default_departments = [
        {"id": uuid.uuid4(), "name": "general", "description": "General plant operations and shared services"},
        {"id": uuid.uuid4(), "name": "process", "description": "Process Engineering, refining units and reactions"},
        {"id": uuid.uuid4(), "name": "maintenance", "description": "Mechanical, rotating equipment & reliability"},
        {"id": uuid.uuid4(), "name": "hse", "description": "Health, Safety & Environmental compliance"},
    ]
    op.bulk_insert(departments_table, default_departments)

    # 4. Seed default roles
    default_roles = [
        {"id": uuid.uuid4(), "name": "engineer", "description": "Standard operator and query analysis access"},
        {"id": uuid.uuid4(), "name": "approver", "description": "Supervisor/manager with sign-off and approval gate authority"},
        {"id": uuid.uuid4(), "name": "admin", "description": "Full administrator with user, model and security management"},
        {"id": uuid.uuid4(), "name": "auditor", "description": "Compliance auditor with complete read-only audit log access"},
    ]
    op.bulk_insert(roles_table, default_roles)


def downgrade() -> None:
    op.drop_index('ix_roles_name', table_name='roles')
    op.drop_table('roles')
    op.drop_index('ix_departments_name', table_name='departments')
    op.drop_table('departments')
