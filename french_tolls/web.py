# -*- coding=utf-8 -*-
"""Entry point for the aiohttp application.

`api.py` builds the application object and is not changed by this work. This
module is only what starts it, so that the image has something to run and the
port is configuration rather than a literal in the request handler.
"""
import logging
import os

from aiohttp import web

from .api import app

logger = logging.getLogger(__name__)

__all__ = ["main"]


def main():
    logging.basicConfig(
        level=os.environ.get("LOG_LEVEL", "INFO"),
        format="[%(asctime)s] %(levelname)-8s [%(name)s] %(message)s",
    )

    web.run_app(app, host="0.0.0.0", port=int(os.environ.get("PORT", "8080")))


if __name__ == "__main__":
    main()
