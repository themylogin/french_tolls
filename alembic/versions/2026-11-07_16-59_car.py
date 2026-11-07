"""car: the car parameters of each Telegram user

Revision ID: c5fd29a893f0
Revises: cd499fbf77cb
Create Date: 2026-11-07 16:59:46.132299

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c5fd29a893f0"
down_revision: Union[str, None] = "cd499fbf77cb"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "car",
        sa.Column("telegram_user_id", sa.Integer(), autoincrement=False, nullable=False),
        sa.Column("fuel_type", sa.Text(), nullable=False),
        sa.Column("tank_volume", sa.Integer(), nullable=False),
        sa.Column("consume_80", sa.Float(), nullable=False),
        sa.Column("consume_130", sa.Float(), nullable=False),
        sa.PrimaryKeyConstraint("telegram_user_id"),
    )


def downgrade() -> None:
    op.drop_table("car")
