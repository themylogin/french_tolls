"""gas stations: the station table, its R*Tree index, and the triggers that keep the index

Revision ID: cd499fbf77cb
Revises: e8eba9c91637
Create Date: 2026-11-07 15:52:59.795794

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "cd499fbf77cb"
down_revision: Union[str, None] = "e8eba9c91637"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "gas_station",
        sa.Column("id", sa.Integer(), autoincrement=False, nullable=False),
        sa.Column("latitude", sa.Float(), nullable=False),
        sa.Column("longitude", sa.Float(), nullable=False),
        sa.Column("name", sa.Text(), nullable=True),
        sa.Column("address", sa.JSON(), nullable=False),
        sa.Column("services", sa.JSON(), nullable=False),
        sa.Column("prices", sa.JSON(), nullable=False),
        sa.Column("last_updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    # The model layer cannot create a virtual table or a trigger, so these
    # statements are written by hand. runtime-store permits it here only.
    op.execute(
        "CREATE VIRTUAL TABLE gas_station_area USING rtree("
        "id, min_latitude, max_latitude, min_longitude, max_longitude)"
    )

    # WARNING: a batch revision that copies gas_station drops these triggers
    # together with the old table. Such a revision must create them again.
    op.execute(
        """
        CREATE TRIGGER gas_station_area_insert AFTER INSERT ON gas_station
        BEGIN
            INSERT INTO gas_station_area
            VALUES (new.id, new.latitude, new.latitude, new.longitude, new.longitude);
        END
        """
    )
    op.execute(
        """
        CREATE TRIGGER gas_station_area_update AFTER UPDATE OF id, latitude, longitude ON gas_station
        BEGIN
            DELETE FROM gas_station_area WHERE id = old.id;
            INSERT INTO gas_station_area
            VALUES (new.id, new.latitude, new.latitude, new.longitude, new.longitude);
        END
        """
    )
    op.execute(
        """
        CREATE TRIGGER gas_station_area_delete AFTER DELETE ON gas_station
        BEGIN
            DELETE FROM gas_station_area WHERE id = old.id;
        END
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER gas_station_area_delete")
    op.execute("DROP TRIGGER gas_station_area_update")
    op.execute("DROP TRIGGER gas_station_area_insert")
    op.execute("DROP TABLE gas_station_area")
    op.drop_table("gas_station")
