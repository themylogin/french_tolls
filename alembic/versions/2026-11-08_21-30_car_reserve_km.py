"""car_reserve_km: the range reserve of each car in km, 50 km for the cars stored before it

Revision ID: 5eebff3c5c55
Revises: 68910fca5c86
Create Date: 2026-11-08 21:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "5eebff3c5c55"
down_revision: Union[str, None] = "68910fca5c86"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("car", schema=None) as batch_op:
        batch_op.add_column(sa.Column("reserve_km", sa.Float(), server_default="50", nullable=False))


def downgrade() -> None:
    with op.batch_alter_table("car", schema=None) as batch_op:
        batch_op.drop_column("reserve_km")
