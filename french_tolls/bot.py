# -*- coding=utf-8 -*-
from dataclasses import dataclass, replace
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
from . import refuel
from .car import CarParameters
from .drive import AskGoogle, AskRoute, Opinion, Part, Stop, drive
from . import spending
from .config import config
from .refine import request_route_once
from .osrm import SNAP_REACH_M, Routers
from .refuel_chat import (GAUGES, no_station_text, no_stop_text, parse_range, station_list, station_paragraph,
                          station_rows)
from .route import (BOOTHS, RouteError, booths_along, get_route, google_maps_link, planned_route, stretch_through,
                    toll_cost)
from .tolls import booths_crossed
from .waypoints import MAX_WAYPOINTS

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
        # The routes a driver can choose between, by the token both buttons carry.
        self.choices = {}
        self.car_dialogs = {}
        # `RefuelOffer`s, by the token their `Plan refuel` button carries.
        self.refuel_offers = {}
        # The open `FuelQuestion` of each driver, by user id, so that a typed range finds it.
        self.fuel_questions = {}
        # Open `StationList`s, by the token their number buttons carry.
        self.station_lists = {}
        self._tokens = itertools.count(1)

    def remember(self, parts):
        """Keep what is still to be driven, and return the token that finds it."""
        token = f"d{next(self._tokens)}"
        self.pending[token] = parts
        return token

    def offer_choice(self, choice):
        """Keep a `Choice`, and return the token that finds it."""
        token = f"r{next(self._tokens)}"
        self.choices[token] = choice
        return token

    def new_car_token(self):
        return f"c{next(self._tokens)}"

    def offer_refuel(self, offer):
        """Keep a `RefuelOffer`, and return the token that finds it."""
        token = f"p{next(self._tokens)}"
        self.refuel_offers[token] = offer
        return token

    def new_gauge_token(self):
        return f"g{next(self._tokens)}"

    def new_list_token(self):
        return f"s{next(self._tokens)}"


@dataclass(frozen=True)
class Choice:
    """The routes an answer offers, and the answer's text, which the press adds to."""

    # As sent, in HTML. The message a press arrives on carries entities instead.
    text: str
    # The parts on offer, by route name.
    parts: dict


@dataclass(frozen=True)
class RefuelOffer:
    """What `Plan refuel` plans on, and the `Drive with Google` beside it."""

    # `optimal`, `super_optimal`, or `fast`, as `route.planned_route` takes it.
    route: str
    # What `Drive with Google` drives, and what a plan that needs no stop drives.
    part: Part
    drive_token: str


@dataclass(frozen=True)
class FuelQuestion:
    token: str
    offer: RefuelOffer
    car: CarParameters
    # Where the question is, so that a typed range can delete it.
    chat_id: int
    message_id: int


@dataclass(frozen=True)
class StationList:
    offer: RefuelOffer
    car: CarParameters
    start: refuel.Start
    # `(latitude, longitude)` of each station chosen before this list, in order.
    chosen: tuple
    # The entries of the plan answer, in the order of the list.
    stations: tuple


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
        state.fuel_questions.pop(user_id, None)
        await handle_location(message=update.message, state=state, location=(
            update.message.location.longitude, update.message.location.latitude))
    elif user_id in state.car_dialogs:
        reply = car_rules.answer_text(state.car_dialogs[user_id], update.message.text)
        await send_car_reply(update.message, state, user_id, reply)
    elif user_id in state.fuel_questions:
        await handle_range(update.message, context, state)
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


def part_of(answer, from_, to, depth=0, name="optimal"):
    """The route `name` of an answer, as the decision reads a stretch to be driven."""
    driven = answer[name]
    booths = driven.get("booths")
    fast_booths = answer["fast"].get("booths")
    waypoints = driven["waypoints"]
    stops = ()
    if name == "super_optimal":
        waypoints = driven["drive_waypoints"]
        stops = tuple(
            Stop(location=(stop["latlon"][1], stop["latlon"][0]),
                 booths=frozenset(stop["booths"]),
                 index=stop["index"])
            for stop in driven["stops"])
    return Part(
        origin=tuple(from_),
        destination=tuple(to),
        cost=driven["cost"],
        waypoints=tuple(tuple(w) for w in waypoints),
        nodes=tuple(tuple(c) for c in driven["nodes"]),
        depth=depth,
        # None where the answer carries no booth set, so a Google route is judged
        # on its road rather than against a set nobody established. An empty list
        # is a different fact and stays one.
        booths=None if booths is None else frozenset(booths),
        fast_booths=None if fast_booths is None else frozenset(fast_booths),
        stops=stops,
    )


async def perform(request):
    """Do what the decision asked for. This is the only place that knows how.
    """
    if isinstance(request, AskRoute):
        try:
            if request.stops:
                answer = await stretch_through(list(request.origin), list(request.destination),
                                               [(stop.location, stop.booths) for stop in request.stops])
                name = "super_optimal"
            else:
                answer = await get_route(list(request.origin), list(request.destination))
                name = "optimal"
        except Exception as e:
            logger.warning("could not route %r -> %r: %r", request.origin, request.destination, e)
            return None
        if answer is None:
            return None
        return part_of(answer, request.origin, request.destination, request.depth, name)

    if isinstance(request, AskGoogle):
        ours = [(lat, lon) for lon, lat in request.nodes]
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
        split = route.get("super_optimal")
        # A split route whose stops alone do not fit in one link cannot be driven.
        offers_split = split is not None and split["drive_waypoints"] is not None
        fast_differs = route["fast"]["nodes"] != route["optimal"]["nodes"]

        text = []
        if offers_split:
            text.append(f"<b>Superoptimal:</b> {format_route(split)}\n")
        text.append(f"<b>Optimal route:</b> {format_route(route['optimal'])}\n")
        text.append(f"<b>Fastest route:</b> {format_route(route['fast'])}\n")
        if offers_split or fast_differs:
            text.append(
                f"➡️ <a href='{html.escape(comparison_map(from_, to))}'>Open comparison map</a>")
        if route["optimal"]["cost"] <= 0:
            text.append("")
            text.append(drive_rules.AVOID_TOLLS)

        # In the order the summaries list them.
        parts = {}
        if offers_split:
            parts["super_optimal"] = part_of(route, from_, to, name="super_optimal")
        parts["optimal"] = part_of(route, from_, to)
        if fast_differs:
            parts["fast"] = part_of(route, from_, to, name="fast")

        if len(parts) > 1:
            token = state.offer_choice(Choice(text="\n".join(text), parts=parts))
            labels = {"super_optimal": "Super", "optimal": "Optimal", "fast": "Fastest"}
            markup = InlineKeyboardMarkup([[InlineKeyboardButton(labels[name], callback_data=f"{token}:{name}")
                                            for name in parts]])
        else:
            part = parts["optimal"]
            markup = drive_and_refuel(state, RefuelOffer(route="optimal", part=part,
                                                         drive_token=state.remember([part])))

        await reply.edit_text("\n".join(text), parse_mode="HTML",
                              reply_markup=markup, disable_web_page_preview=True)
    except Exception as e:
        logger.warning("Error: %r", e, exc_info=True)
        await reply.edit_text("Error calculating this route. I am very sorry for that 😞")


async def choice_button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    token, _, name = query.data.partition(":")
    state = state_of(context)
    choice = state.choices.pop(token, None)
    if choice is None:
        await query.edit_message_reply_markup(reply_markup=None)
        await query.message.reply_text("That route has expired. Please send the locations again.")
        return

    part = choice.parts[name]
    label = {"super_optimal": "Superoptimal", "optimal": "Optimal", "fast": "Fastest"}[name]
    markup = drive_and_refuel(state, RefuelOffer(route=name, part=part, drive_token=state.remember([part])))
    await query.edit_message_text(f"{choice.text}\n\n{label} route chosen", parse_mode="HTML",
                                  reply_markup=markup, disable_web_page_preview=True)


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
    for token in [token for token, offer in state.refuel_offers.items() if offer.drive_token == query.data]:
        del state.refuel_offers[token]

    head, rest = parts[0], parts[1:]
    settled = drive_rules.settle(head, google_maps_link)
    if settled is not None:
        outcome = drive_rules.Outcome(messages=[settled], pending=list(rest))
        await send_outcome(query.message, state, outcome, whole=head.depth == 0 and not rest)
        return

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


def drive_and_refuel(state, offer):
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("Drive with Google", callback_data=offer.drive_token),
        InlineKeyboardButton("Plan refuel", callback_data=state.offer_refuel(offer)),
    ]])


async def expire_refuel_button(query):
    await query.edit_message_reply_markup(reply_markup=None)
    await query.message.reply_text("That route has expired. Please send the locations again.")


async def plan_refuel_button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    state = state_of(context)
    user_id = query.from_user.id
    offer = state.refuel_offers.get(query.data)
    if offer is None:
        await expire_refuel_button(query)
        return

    parameters = await car_rules.load_car(user_id)
    if parameters is None:
        await query.message.reply_text("Use /car to set up your car details in order to use this.")
        return

    # One flow at a time: the answer's `Drive with Google` is spent with it.
    del state.refuel_offers[query.data]
    state.pending.pop(offer.drive_token, None)
    await query.edit_message_reply_markup(reply_markup=None)

    token = state.new_gauge_token()
    markup = InlineKeyboardMarkup([
        [InlineKeyboardButton(label, callback_data=f"{token}:{step}") for label, step in row]
        for row in GAUGES[parameters.gauge_steps]
    ])
    question = await query.message.reply_text(
        "How much fuel do you have? Choose it on the gauge or enter the range in kilometers.", reply_markup=markup)
    state.fuel_questions[user_id] = FuelQuestion(token=token, offer=offer, car=parameters,
                                                 chat_id=question.chat_id, message_id=question.message_id)


async def gauge_button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    state = state_of(context)
    user_id = query.from_user.id
    token, _, step = query.data.partition(":")
    question = state.fuel_questions.get(user_id)
    if (question is None or question.token != token
            or int(step) not in {value for row in GAUGES[question.car.gauge_steps] for _label, value in row}):
        await expire_refuel_button(query)
        return

    del state.fuel_questions[user_id]
    await query.message.delete()
    start = refuel.Start(0, fuel=question.car.tank_volume * int(step) / question.car.gauge_steps)
    await plan_and_answer(query.message, state, question.offer, question.car, start, ())


async def handle_range(message, context, state):
    user_id = message.from_user.id
    range_km = parse_range(message.text)
    if range_km is None:
        await message.reply_text("Choose it on the gauge or enter the range in kilometers, for example 120.")
        return

    question = state.fuel_questions.pop(user_id)
    await context.bot.delete_message(chat_id=question.chat_id, message_id=question.message_id)
    await plan_and_answer(message, state, question.offer, question.car, refuel.Start(0, range_km=range_km), ())


async def station_button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    state = state_of(context)
    token, _, number = query.data.partition(":")
    listed = state.station_lists.pop(token, None)
    if listed is None or not 1 <= int(number) <= len(listed.stations):
        await expire_refuel_button(query)
        return

    station = listed.stations[int(number) - 1]
    paragraph = station_paragraph(int(number), station)
    await query.edit_message_text(paragraph, parse_mode="HTML", disable_web_page_preview=True)
    chosen = (*listed.chosen, (station["latitude"], station["longitude"]))
    await plan_and_answer(query.message, state, listed.offer, listed.car, listed.start, chosen, paragraph)


async def plan_stops(offer, parameters, start, chosen):
    """The planner's answer, and the `Part` that drives a finished plan through its stations.

    The `Part` is None until the plan is finished, and where its stops do not fit
    in one link.
    """
    routers = Routers()
    origin, destination = list(offer.part.origin), list(offer.part.destination)
    planned = await planned_route(routers, origin, destination, offer.route)
    if planned is None:
        raise RouteError("no_route", "the journey has no split route any more")

    answer = await refuel.plan(routers, planned, parameters, toll_cost, fuel=start.fuel, range_km=start.range_km,
                               chosen=chosen)
    if answer["stop_needed"] or not chosen:
        return answer, None

    finished, vias, _start = await refuel.through_chosen(routers, planned, parameters, start, chosen)
    if offer.route == "fast":
        return answer, fast_plan_part(offer.part, finished, vias)

    stretch = await stretch_through(origin, destination, [(via.location, frozenset(via.booths)) for via in vias])
    if stretch is None:
        raise RouteError("no_route", "the route through the stations misses a split stop")
    if stretch["super_optimal"]["drive_waypoints"] is None:
        return answer, None
    return answer, part_of(stretch, origin, destination, name="super_optimal")


def fast_plan_part(part, finished, vias):
    """A finished plan on the fastest route, or None where its stations do not fit in one link.

    Its booths are those of its own fastest route, so rule 1 or rule 2 always
    settles it: one link through the stations, as Google drives them fastest.
    """
    if len(vias) > MAX_WAYPOINTS:
        return None

    booths = frozenset(booths_crossed(BOOTHS, finished.node_ids))
    stops = tuple(Stop(location=tuple(via.location), booths=frozenset(), index=via.index) for via in vias)
    return replace(part, cost=toll_cost(finished), nodes=tuple(tuple(c) for c in finished.coordinates),
                   waypoints=tuple(stop.location for stop in stops), booths=booths, fast_booths=booths, stops=stops)


async def plan_and_answer(message, state, offer, parameters, start, chosen, paragraph=None):
    """Plan, and send the answer: a list to choose from, or what to drive.

    After a station press, `message` is that station's `paragraph`, which a finished plan offers to drive.
    """
    working = await message.reply_text("⏳ Finding gas stations...")
    try:
        answer, part = await plan_stops(offer, parameters, start, chosen)
    except Exception as e:
        logger.warning("Error planning a refuel: %r", e, exc_info=True)
        await working.edit_text("Error finding gas stations. I am very sorry for that 😞")
        return

    if not answer["stop_needed"] and not chosen:
        await working.edit_text(no_stop_text(answer),
                                reply_markup=keyboard("Drive with Google", state.remember([offer.part])))
        return
    if not answer["stop_needed"] and part is None:
        await working.edit_text("The refuel plan has too many stops for one Google Maps link.")
        return
    if not answer["stop_needed"]:
        await working.delete()
        await message.edit_text(paragraph, parse_mode="HTML", disable_web_page_preview=True,
                                reply_markup=keyboard("Drive with Google", state.remember([part])))
        return
    if not answer["stations"]:
        await working.edit_text(no_station_text(parameters))
        return

    token = state.new_list_token()
    state.station_lists[token] = StationList(offer=offer, car=parameters, start=start, chosen=tuple(chosen),
                                             stations=tuple(answer["stations"]))
    markup = InlineKeyboardMarkup([
        [InlineKeyboardButton(label, callback_data=f"{token}:{label}") for label in row]
        for row in station_rows(len(answer["stations"]))
    ])
    await working.edit_text(station_list(answer["stations"]), parse_mode="HTML", reply_markup=markup,
                            disable_web_page_preview=True)


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
    state_of(context).fuel_questions.pop(update.message.from_user.id, None)
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
    application.add_handler(CallbackQueryHandler(choice_button_handler,
                                                 pattern=r"^r\d+:(optimal|super_optimal|fast)$"))
    application.add_handler(CallbackQueryHandler(car_button_handler, pattern=r"^car:"))
    application.add_handler(CallbackQueryHandler(plan_refuel_button_handler, pattern=r"^p\d+$"))
    application.add_handler(CallbackQueryHandler(gauge_button_handler, pattern=r"^g\d+:\d+$"))
    application.add_handler(CallbackQueryHandler(station_button_handler, pattern=r"^s\d+:\d+$"))

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
    logging.getLogger("aiosqlite").setLevel(logging.WARNING)

    main()
