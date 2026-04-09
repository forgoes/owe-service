"""add conversation state columns

Revision ID: 13f5d9ee6ac2
Revises: accb5327bbbc
Create Date: 2026-04-07 19:15:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "13f5d9ee6ac2"
down_revision: Union[str, Sequence[str], None] = "accb5327bbbc"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "conversations",
        sa.Column("missing_fields_json", sa.Text(), nullable=False, server_default="[]"),
        schema="owe",
    )
    op.add_column(
        "conversations",
        sa.Column("next_question", sa.Text(), nullable=False, server_default=""),
        schema="owe",
    )
    op.add_column(
        "conversations",
        sa.Column("last_intent", sa.String(length=64), nullable=True),
        schema="owe",
    )


def downgrade() -> None:
    op.drop_column("conversations", "last_intent", schema="owe")
    op.drop_column("conversations", "next_question", schema="owe")
    op.drop_column("conversations", "missing_fields_json", schema="owe")
