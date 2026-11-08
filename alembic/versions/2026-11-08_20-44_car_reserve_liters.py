"""car_reserve_liters: the reserve of each car in liters, 5 L for the cars stored before it, the km values dropped

Revision ID: 68910fca5c86
Revises: f99c669a7732
Create Date: 2026-11-08 20:44:50.299300

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "68910fca5c86"
down_revision: Union[str, None] = "f99c669a7732"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("car", schema=None) as batch_op:
        batch_op.drop_column("reserve_km")
        batch_op.add_column(sa.Column("reserve", sa.Float(), server_default="5", nullable=False))


def downgrade() -> None:
    with op.batch_alter_table("car", schema=None) as batch_op:
        batch_op.drop_column("reserve")
        batch_op.add_column(sa.Column("reserve_km", sa.Float(), server_default="50", nullable=False))
