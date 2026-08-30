"""baseline: the autocomplete cache and the monthly request count

Revision ID: e8eba9c91637
Revises:
Create Date: 2026-08-30 17:46:44.332818

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e8eba9c91637"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "autocomplete",
        sa.Column("q", sa.Text(), nullable=False),
        sa.Column("response", sa.JSON(), nullable=False),
        sa.PrimaryKeyConstraint("q"),
    )
    op.create_table(
        "google_requests",
        sa.Column("year_month", sa.Text(), nullable=False),
        sa.Column("count", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("year_month"),
    )


def downgrade() -> None:
    op.drop_table("google_requests")
    op.drop_table("autocomplete")
