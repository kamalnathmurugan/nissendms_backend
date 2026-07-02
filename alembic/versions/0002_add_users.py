"""add users table

Revision ID: 0002
Revises: 0001
Create Date: 2026-07-02
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("azure_oid", sa.String(length=256), nullable=False),
        sa.Column("tenant_id", sa.String(length=256), nullable=True),
        sa.Column("email", sa.String(length=320), nullable=True),
        sa.Column("display_name", sa.String(length=320), nullable=True),
        sa.Column("given_name", sa.String(length=160), nullable=True),
        sa.Column("surname", sa.String(length=160), nullable=True),
        sa.Column("preferred_username", sa.String(length=320), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("last_login_at", sa.DateTime(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("azure_oid"),
    )
    op.create_index("ix_users_azure_oid", "users", ["azure_oid"])
    op.create_index("ix_users_email", "users", ["email"])


def downgrade() -> None:
    op.drop_index("ix_users_email", table_name="users")
    op.drop_index("ix_users_azure_oid", table_name="users")
    op.drop_table("users")
