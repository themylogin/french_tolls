# -*- coding=utf-8 -*-
from dataclasses import dataclass
import os

__all__ = ["config"]

GOOGLE_ROUTES = "https://routes.googleapis.com/directions/v2:computeRoutes"


def getenv(name, default=""):
    return os.environ.get(name, "").strip() or default


@dataclass(frozen=True)
class Config:
    # Public address of the site.
    url: str = getenv("URL").rstrip("/")

    telegram_bot_token: str = getenv("TELEGRAM_BOT_TOKEN")

    # Place lookup for the search box.
    locationiq_api_key: str = getenv("LOCATIONIQ_API_KEY")

    google_api_key: str = getenv("GOOGLE_DIRECTIONS_API_KEY")

    # Paid Google requests allowed per calendar month.
    google_max_requests_per_month: int = int(getenv("GOOGLE_DIRECTIONS_MAX_REQUEST_PER_MONTH", "0"))

    # Where route requests are sent. A setting so the integration suite can point
    # the real client at its own replay server.
    google_routes_endpoint: str = getenv("GOOGLE_ROUTES_ENDPOINT", GOOGLE_ROUTES)

    # OSRM's travel time is multiplied by this before it is served. Google
    # predicts x0.9333 of OSRM's time for the same road; 1 serves it unchanged.
    time_multiplier: float = float(getenv("TIME_MULTIPLIER", "1"))

    # What a driver's hour is worth.
    eur_per_hour: float = float(getenv("EUR_PER_HOUR", "20"))

    # Debug mode. The effects:
    #   - the page draws Google's route in orange under ours, and a dot per waypoint:
    #     orange for one added while comparing the optimal route with the fastest one,
    #     purple for one added while comparing the result with Google Directions API route.
    debug: bool = getenv("DEBUG").lower() in ("1", "true", "yes", "on")

    log_level: str = getenv("LOG_LEVEL", "INFO")


config = Config()
