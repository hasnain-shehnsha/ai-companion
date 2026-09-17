"""fix missing usage_records table

Revision ID: 86638260fff1
Revises: f3d995c0d659
Create Date: 2026-09-16 10:36:14.063311

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.engine.reflection import Inspector


# revision identifiers, used by Alembic.
revision: str = "86638260fff1"
down_revision: Union[str, Sequence[str], None] = "f3d995c0d659"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    conn = op.get_bind()
    inspector = Inspector.from_engine(conn)
    tables = inspector.get_table_names()
    if "usage_records" not in tables:
        op.create_table(
            "usage_records",
            sa.Column("id", sa.String(), nullable=False),
            sa.Column("user_id", sa.String(), nullable=True),
            sa.Column("model", sa.String(), nullable=False),
            sa.Column("input_tokens", sa.Integer(), nullable=True, server_default="0"),
            sa.Column("output_tokens", sa.Integer(), nullable=True, server_default="0"),
            sa.Column("request_type", sa.String(), nullable=False),
            sa.Column("channel", sa.String(), nullable=False),
            sa.Column(
                "estimated_cost", sa.Float(), nullable=True, server_default="0.0"
            ),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=True,
            ),
            sa.ForeignKeyConstraint(
                ["user_id"],
                ["users.id"],
            ),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(
            op.f("ix_usage_records_id"), "usage_records", ["id"], unique=False
        )


def downgrade() -> None:
    """Downgrade schema."""
    conn = op.get_bind()
    inspector = Inspector.from_engine(conn)
    tables = inspector.get_table_names()
    if "usage_records" in tables:
        op.drop_index(op.f("ix_usage_records_id"), table_name="usage_records")
        op.drop_table("usage_records")
