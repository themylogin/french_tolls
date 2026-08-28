# -*- coding=utf-8 -*-
import logging

from aiohttp import web

from .autocomplete import autocomplete
from .service import RouteError, get_route, refined_link

logger = logging.getLogger(__name__)

__all__ = ["app"]

# The three shapes a directions link can take, and what each does with the
# route's own origin. They are the three the answer has always named.
FORMS = ("start", "here", "here-via-start")


async def calculate(request):
    data = await request.json()

    return web.json_response(await get_route(data["from"], data["to"]))


async def refine(request):
    """The refinement for a journey, and a route to draw for it.

    This is what the page's control calls, and the only caller that asks for the
    geometry. Drawing needs Google's route through the *refined* waypoints, which
    does not exist until it is asked for — the first request cannot answer it,
    since its whole purpose is to find where that route will differ. So this
    costs two requests for a journey nobody has looked at yet, and none for one
    already bought.
    """
    data = await request.json()

    try:
        answer, refinement, url = await refined_link(
            data["from"], data["to"], with_geometry=True)
    except RouteError as e:
        return web.json_response({"error": e.cause, "message": str(e)}, status=400)

    return web.json_response({
        "url": url,
        **refinement.as_dict(),
        "ours": {
            "distance": answer["optimal"]["distance"],
            "duration": answer["optimal"]["duration"],
            "waypoints": answer["optimal"]["waypoints"],
        },
    })


def _point(raw):
    """`lon,lat` from a query string, as the API takes coordinates."""
    lon, lat = raw.split(",")
    return [float(lon), float(lat)]


async def go(request):
    """Refine, then send the browser to Google Maps.

    This is where the three link keys point. Refining when a link is *followed*
    rather than when it is written is what keeps a link nobody clicks from
    costing anything: the bot writes them long before anyone opens one.

    It redirects whether or not the refinement happened. A link that fails
    because a budget was exhausted is worse than a link that is merely no better
    than it was.
    """
    form = request.match_info["form"]
    if form not in FORMS:
        raise web.HTTPNotFound(text=f"unknown link form {form!r}")

    try:
        from_ = _point(request.query["from"])
        to = _point(request.query["to"])
    except (KeyError, ValueError):
        raise web.HTTPBadRequest(text="from and to are required, each as lon,lat")

    try:
        _answer, refinement, url = await refined_link(from_, to, form)
    except RouteError as e:
        raise web.HTTPBadRequest(text=str(e))

    logger.info("go/%s %s -> %s: refined=%s %s", form, from_, to,
                refinement.refined, refinement.reason or "")

    raise web.HTTPFound(url)


app = web.Application()
app.add_routes([web.get("/api/autocomplete", autocomplete)])
app.add_routes([web.post("/api/calculate", calculate)])
app.add_routes([web.post("/api/refine", refine)])
app.add_routes([web.get("/go/{form}", go)])
