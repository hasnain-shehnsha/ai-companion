"""add_partially_sent_reminder_status

Revision ID: c498f48a21a4
Revises: 3ba72d322a68
Create Date: 2026-09-16 14:37:07.445631

"""

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "c498f48a21a4"
down_revision: Union[str, Sequence[str], None] = "3ba72d322a68"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add PARTIALLY_SENT value to the reminderstatus enum."""
    op.execute("ALTER TYPE reminderstatus ADD VALUE IF NOT EXISTS 'PARTIALLY_SENT'")


def downgrade() -> None:
    """PostgreSQL does not support removing enum values. No-op."""
    pass
