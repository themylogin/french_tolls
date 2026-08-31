# -*- coding=utf-8 -*-
"""The schema, for a suite that has its own cache and no migration service.

`web` and `bot` wait on the one-shot `migrate` run, because they share one file
and start together. This suite shares nothing: its cache is a tmpfs that is
created empty and dies with the run, so there is no other process to race and no
reason to make `docker compose run integration` two commands.

Applied through alembic rather than `create_all`, so the suite exercises the same
revisions a deployment does. A revision that fails here fails before it reaches
the volume that matters.
"""
import os

from alembic import command
from alembic.config import Config
import pytest


@pytest.fixture(scope="session", autouse=True)
def schema():
    ini = os.path.join(os.path.dirname(__file__), os.pardir, os.pardir, "alembic.ini")
    command.upgrade(Config(os.path.abspath(ini)), "head")
