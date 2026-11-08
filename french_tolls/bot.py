# -*- coding=utf-8 -*-
import html
import itertools
import json
import logging
from pathlib import Path
import re
import urllib.parse

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (Application, CallbackQueryHandler, CommandHandler, ContextTypes,
                          filters, MessageHandler)

from . import car as car_rules
from . import drive as drive_rules
from .drive import AskGoogle, AskRoute, Opinion, Part, drive
from . import spending
from .config import config
from .refine import request_route_once
from .osrm import SNAP_REACH_M, Routers
from .route import booths_along, get_route, google_maps_link

logger = logging.getLogger(__name__)

TOO_FAR = "🇫🇷 This location is not within a kilometer of any road in France"

# The words on the link a part carries. A driver sent one stretch of four
# should not be told to drive "this route".
DRIVE_THIS = "Drive this route"
DRIVE_NEXT_PART = "Drive the next part of the route"
DRIVE_FINAL_PART = "Drive the final part of the route"

# The share of Google's route that has to run inside our corridor before a link
# counts as one a driver can follow.
FIT_THRESHOLD = 0.98


class ChatState:
    """What the exchange is holding, for one application.
    """

    def __init__(self):
        # The origin each driver has sent, by user id, until they send a
        # destination.
        self.users_from = {}
        # Stretches offered but not yet asked for, by the token the button
        # carries.
        self.pending = {}
        self.car_dialogs = {}
        self._tokens = itertools.count(1)

    def remember(self, parts):
        """Keep what is still to be driven, and return the token that finds it."""
        token = f"d{next(self._tokens)}"
        self.pending[token] = parts
        return token

    def new_car_token(self):
        return f"c{next(self._tokens)}"


def state_of(context) -> ChatState:
    """The state belonging to the application this update reached."""
    return context.bot_data[STATE_KEY]


STATE_KEY = "french_tolls_chat_state"


# `lat, lon` as a driver types it, or pastes it out of Google Maps.
NUMBER = r"(?<![\d.])(-?\d+(?:\.\d+)?)(?![\d.])"
COORDINATES = re.compile(rf"{NUMBER}\s*,\s*{NUMBER}")


def parse_location(text):
    """`(longitude, latitude)` from text, or None.
    """
    if m := COORDINATES.search(text):
        return float(m.group(2)), float(m.group(1))


async def text_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message is None:
        return

    state = state_of(context)
    user_id = update.message.from_user.id
    if update.message.location is not None:
        await handle_location(message=update.message, state=state, location=(
            update.message.location.longitude, update.message.location.latitude))
    elif user_id in state.car_dialogs:
        reply = car_rules.answer_text(state.car_dialogs[user_id], update.message.text)
        await send_car_reply(update.message, state, user_id, reply)
    elif location := parse_location(update.message.text):
        await handle_location(update.message, state, location)
    else:
        await send_help(update.message)


async def handle_location(message, state, location):
    user_id = message.from_user.id

    try:
        distance = await Routers().distance_to_road_network(location)
    except Exception as e:
        logger.error("Exception while calculating distance to road network for %r: %r", location, e)
        await message.reply_text(TOO_FAR)
        return
    else:
        if distance > SNAP_REACH_M:
            await message.reply_text(TOO_FAR)
            return

    if user_id in state.users_from:
        from_ = state.users_from.pop(user_id)
        await handle_route(message, state, from_, location)
    else:
        state.users_from[user_id] = location
        await message.reply_text("Now, send me the destination location")


def format_route(route):
    duration = []
    if route["duration"] >= 3600:
        duration.append(f"{int(route['duration'] / 3600)}h")
    if m := int(route["duration"] % 3600 / 60):
        duration.append(f"{m}min")
    duration = " ".join(duration) or "1min"

    return f"{duration}, {route['cost']:0.2f} €\n{int(route['distance'] / 1000)} km"


def comparison_map(from_, to):
    """The page, showing both routes for this journey."""
    hash = urllib.parse.quote(json.dumps({
        "from": {"name": "Telegram location", "lonlat": list(from_)},
        "to": {"name": "Telegram location", "lonlat": list(to)},
    }))
    return f"{config.url}/#{hash}"


def part_of(answer, from_, to, depth=0):
    """The optimal route, as the decision reads a stretch to be driven."""
    optimal = answer["optimal"]
    booths = optimal.get("booths")
    fast_booths = answer["fast"].get("booths")
    return Part(
        origin=tuple(from_),
        destination=tuple(to),
        cost=optimal["cost"],
        waypoints=tuple(tuple(w) for w in optimal["waypoints"]),
        nodes=tuple(tuple(c) for c in optimal["nodes"]),
        depth=depth,
        # None where the answer carries no booth set, so a Google route is judged
        # on its road rather than against a set nobody established. An empty list
        # is a different fact and stays one.
        booths=None if booths is None else frozenset(booths),
        fast_booths=None if fast_booths is None else frozenset(fast_booths),
    )


async def perform(request):
    """Do what the decision asked for. This is the only place that knows how.
    """
    if isinstance(request, AskRoute):
        try:
            answer = await get_route(list(request.origin), list(request.destination))
        except Exception as e:
            logger.warning("could not route %r -> %r: %r", request.origin, request.destination, e)
            return None
        return part_of(answer, request.origin, request.destination, request.depth)

    if isinstance(request, AskGoogle):
        try:
            answer = await get_route(list(request.origin), list(request.destination))
        except Exception as e:
            logger.warning("could not route for a Google request: %r", e)
            return None
        ours = [(lat, lon) for lon, lat in answer["optimal"]["nodes"]]
        google = await request_route_once(list(request.origin), list(request.destination),
                                          ours, [list(w) for w in request.waypoints])
        if google is None:
            return None

        booths = await booths_along(google.geometry)
        return Opinion(
            share=google.share,
            waypoints=tuple(tuple(w) for w in google.waypoints),
            booths=booths,
        )

    raise AssertionError(f"unknown request {request!r}")


async def resolve(part, budget):
    """Run the decision to its end, performing what it asks for."""
    generator = drive(part, budget, lambda share: share >= FIT_THRESHOLD, google_maps_link)
    try:
        request = generator.send(None)
        while True:
            request = generator.send(await perform(request))
    except StopIteration as stop:
        return stop.value


def keyboard(label, token):
    return InlineKeyboardMarkup([[InlineKeyboardButton(label, callback_data=token)]])


async def send_outcome(message, state, outcome, whole):
    """Send what was settled, and offer an action for what was not."""
    for index, sent in enumerate(outcome.messages):
        last = index == len(outcome.messages) - 1
        if whole:
            label = DRIVE_THIS
        elif last and not outcome.pending:
            label = DRIVE_FINAL_PART
        else:
            label = DRIVE_NEXT_PART
        logger.info("sending a part accepted on %s",
                    sent.basis or "neither test; it is the best link there was")
        text = "\n".join(filter(None, [sent.text, f"➡️ <a href='{html.escape(sent.link)}'>{label}</a>"]))
        markup = None
        if last and outcome.pending:
            markup = keyboard("Click here when you have finished",
                              state.remember(outcome.pending))
        await message.reply_text(text, parse_mode="HTML", reply_markup=markup,
                                 disable_web_page_preview=True)


async def handle_route(message, state, from_, to):
    reply = await message.reply_text("⏳ Calculating route...")
    try:
        route = await get_route(from_, to)

        text = []
        text.append(f"<b>Optimal route:</b> {format_route(route['optimal'])}\n")
        text.append(f"<b>Fastest route:</b> {format_route(route['fast'])}\n")
        # If routes are different, offer the comparison map.
        if route["fast"]["nodes"] != route["optimal"]["nodes"]:
            text.append(
                f"➡️ <a href='{html.escape(comparison_map(from_, to))}'>Open comparison map</a>")
        if route["optimal"]["cost"] <= 0:
            text.append("")
            text.append(drive_rules.AVOID_TOLLS)

        part = part_of(route, from_, to)
        # Nothing to ask Google about, so there is nothing to press for either.
        # The link goes in this message rather than in one of its own.
        if drive_rules.pays_no_tolls(part) or drive_rules.routes_agree(part):
            link = drive_rules.link_from_here(part, (), google_maps_link)
            text.append(f"➡️ <a href='{html.escape(link)}'>{DRIVE_THIS}</a>")
            markup = None
        else:
            markup = keyboard("Drive with Google", state.remember([part]))

        await reply.edit_text("\n".join(text), parse_mode="HTML",
                              reply_markup=markup, disable_web_page_preview=True)
    except Exception as e:
        logger.warning("Error: %r", e, exc_info=True)
        await reply.edit_text("Error calculating this route. I am very sorry for that 😞")


async def drive_button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    state = state_of(context)
    parts = state.pending.pop(query.data, None)
    if parts is None:
        await query.edit_message_reply_markup(reply_markup=None)
        await query.message.reply_text("That route has expired. Please send the locations again.")
        return

    # The button is spent: a second press would pay for the same answer twice.
    await query.edit_message_reply_markup(reply_markup=None)

    head, rest = parts[0], parts[1:]
    working = await query.message.reply_text("⏳ Checking with Google...")
    try:
        outcome = await resolve(head, await remaining_budget())
    except Exception as e:
        logger.warning("Error driving: %r", e, exc_info=True)
        await working.edit_text("Error preparing this route. I am very sorry for that 😞")
        return

    await working.delete()
    outcome.pending = outcome.pending + rest
    whole = head.depth == 0 and not outcome.pending and len(outcome.messages) == 1
    await send_outcome(query.message, state, outcome, whole)


async def remaining_budget():
    """How many Google requests are left this month.
    """
    spent = await spending.google_requests_this_month()
    return max(0, config.google_max_requests_per_month - spent)


async def help_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await send_help(update.message)


async def send_help(message):
    await message.reply_text(
        f"This is a bot that will calculate a route within mainland France that uses toll roads but will not be too "
        f"expensive (it assumes an hour of driving time is worth 20 EUR).\n\n"

        "Just send the origin and the destination locations, and it will calculate the route.\n\n"

        f"The full version is available here: {config.url}\n\n"

        "You can send me a tip using this link: https://buymeacoffee.com/themylogin or https://paypal.me/themyloginspain"
    )


async def car_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    state = state_of(context)
    user_id = update.message.from_user.id
    reply = car_rules.start(state.new_car_token(), await car_rules.load_car(user_id))
    await send_car_reply(update.message, state, user_id, reply)


async def car_button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    token, _, choice = query.data.removeprefix("car:").partition(":")
    state = state_of(context)
    user_id = query.from_user.id
    reply = car_rules.answer_button(state.car_dialogs.get(user_id), token, choice)
    if reply.pressed_text is None:
        await query.edit_message_reply_markup(reply_markup=None)
    elif query.message.photo:
        await query.edit_message_caption(caption=reply.pressed_text)
    else:
        await query.edit_message_text(reply.pressed_text)

    await send_car_reply(query.message, state, user_id, reply)


async def send_car_reply(message, state, user_id, reply):
    if reply.save is not None:
        try:
            await car_rules.save_car(user_id, reply.save)
        except Exception as e:
            logger.warning("Error saving the car of %r: %r", user_id, e, exc_info=True)
            state.car_dialogs.pop(user_id, None)
            await message.reply_text("Error saving your car parameters. I am very sorry for that 😞")
            return

    if reply.dialog is None:
        state.car_dialogs.pop(user_id, None)
    else:
        state.car_dialogs[user_id] = reply.dialog

    markup = None
    if reply.buttons:
        markup = InlineKeyboardMarkup([
            [InlineKeyboardButton(label, callback_data=f"car:{reply.dialog.token}:{choice}") for label, choice in row]
            for row in reply.buttons
        ])
    if reply.photo:
        gauges = Path(__file__).parent / "assets" / "gauges.png"
        await message.reply_photo(photo=gauges.read_bytes(), caption=reply.text, reply_markup=markup)
    else:
        await message.reply_text(reply.text, reply_markup=markup)


async def reset_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    state_of(context).users_from.pop(update.message.from_user.id, None)
    await update.message.reply_text("Now, send me the origin location")


async def post_init(application: Application):
    await application.bot.set_my_commands([
        ("help", "Help"),
        ("reset", "Reset the origin location"),
        ("car", "Enter car parameters"),
    ])


def build(token, *, request=None, get_updates_request=None):
    builder = Application.builder().token(token).post_init(post_init)
    if request is not None:
        builder = builder.request(request)
    if get_updates_request is not None:
        builder = builder.get_updates_request(get_updates_request)

    application = builder.build()
    application.bot_data[STATE_KEY] = ChatState()

    application.add_handler(MessageHandler((filters.TEXT | filters.LOCATION) & ~filters.COMMAND, text_message_handler))
    application.add_handler(CommandHandler("help", help_command_handler))
    application.add_handler(CommandHandler("reset", reset_command_handler))
    application.add_handler(CommandHandler("car", car_command_handler))
    application.add_handler(CallbackQueryHandler(drive_button_handler, pattern=r"^d\d+$"))
    application.add_handler(CallbackQueryHandler(car_button_handler, pattern=r"^car:"))

    return application


def main():
    for name, value in (("TELEGRAM_BOT_TOKEN", config.telegram_bot_token),
                        ("URL", config.url)):
        if not value:
            raise SystemExit(f"french_tolls: cannot start: {name} is not set")

    build(config.telegram_bot_token).run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG, format="[%(asctime)s] %(levelname)-8s [%(name)s] %(message)s")
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("telegram").setLevel(logging.WARNING)

    main()
