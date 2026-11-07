# -*- coding=utf-8 -*-
import logging

from aiohttp import web

from .api import app
from .config import config

logger = logging.getLogger(__name__)

__all__ = ["main"]


def main():
    logging.basicConfig(
        level=config.log_level,
        format="[%(asctime)s] %(levelname)-8s [%(name)s] %(message)s",
    )

    # aiohttp refuses a request line over 8 KB by default. /api/osrm/ proxies requests with path up to 120 KB.
    web.run_app(app, host="0.0.0.0", port=8080, max_line_size=1048576)


if __name__ == "__main__":
    main()
