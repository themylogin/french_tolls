"""car_drop_reserve_liters: one reserve per car, in km; the reserves in liters are dropped

Revision ID: 03a4ddfa6d68
Revises: 5eebff3c5c55
Create Date: 2026-11-09 15:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "03a4ddfa6d68"
down_revision: Union[str, None] = "5eebff3c5c55"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("car", schema=None) as batch_op:
        batch_op.drop_column("reserve")


def downgrade() -> None:
    with op.batch_alter_table("car", schema=None) as batch_op:
        batch_op.add_column(sa.Column("reserve", sa.Float(), server_default="5", nullable=False))
