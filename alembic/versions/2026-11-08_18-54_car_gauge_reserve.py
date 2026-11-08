"""car_gauge_reserve: the gauge and the reserve of each car, 16 steps and 50 km for the cars stored before them

Revision ID: f99c669a7732
Revises: c5fd29a893f0
Create Date: 2026-11-08 18:54:57.174081

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f99c669a7732"
down_revision: Union[str, None] = "c5fd29a893f0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("car", schema=None) as batch_op:
        batch_op.add_column(sa.Column("gauge_steps", sa.Integer(), server_default="16", nullable=False))
        batch_op.add_column(sa.Column("reserve_km", sa.Float(), server_default="50", nullable=False))


def downgrade() -> None:
    with op.batch_alter_table("car", schema=None) as batch_op:
        batch_op.drop_column("reserve_km")
        batch_op.drop_column("gauge_steps")
