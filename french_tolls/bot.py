# -*- coding=utf-8 -*-
import html
import json
import logging
import os
import re
import urllib.parse

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, filters, MessageHandler

from .route import distance_to_road_network
from .service import get_route

logger = logging.getLogger(__name__)

users_from = {}


def parse_location(text):
    if m := re.search(r"([0-9.]+),\s*([0-9.]+)", text):
        return float(m.group(2)), float(m.group(1))


async def text_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message is None:
        return

    if update.message.location is not None:
        await handle_location(update.message, (update.message.location.longitude, update.message.location.latitude))
    elif location := parse_location(update.message.text):
        await handle_location(update.message, location)
    else:
        await send_help(update.message)


async def handle_location(message, location):
    user_id = message.from_user.id

    try:
        distance = await distance_to_road_network(location)
    except Exception as e:
        logger.error("Exception while calculating distance to road network for %r: %r", location, e)
        await message.reply_text("This location is not within a kilometer of any road in France")
        return
    else:
        if distance > 1000:
            await message.reply_text("This location is not within a kilometer of any road in France")
            return

    if user_id in users_from:
        from_ = users_from.pop(user_id)
        await handle_route(message, from_, location)
    else:
        users_from[user_id] = location
        await message.reply_text("Now, send me the destination location")


def format_route(route):
    duration = []
    if route["duration"] >= 3600:
        duration.append(f"{int(route['duration'] / 3600)}h")
    if m := int(route["duration"] % 3600 / 60):
        duration.append(f"{m}min")
    duration = " ".join(duration) or "1min"

    return f"{duration}, {route['cost']:0.2f} €\n{int(route['distance'] / 1000)} km"


async def handle_route(message, from_, to):
    reply = await message.reply_text("⏳ Calculating route...")
    try:
        route = await get_route(from_, to)

        hash = html.escape(urllib.parse.quote(json.dumps({
            "from": {
                "name": "Telegram location",
                "lonlat": from_,
            },
            "to": {
                "name": "Telegram location",
                "lonlat": to,
            },
        })))

        text = []
        text.append(f"<b>Optimal route:</b> {format_route(route['optimal'])}\n")
        text.append(f"<b>Fastest route:</b> {format_route(route['fast'])}\n")
        text.append(f"<b>Google Maps Links</b>:")
        text.append(f"➡️ <a href='{html.escape(route['optimal']['url_from_current_location'])}'>From your location</a>")
        text.append(f"➡️ <a href='{html.escape(route['optimal']['url_from_current_location_through_start'])}'>From your location through route start</a>")
        text.append(f"➡️ <a href='{html.escape(route['optimal']['url'])}'>From route start</a>\n")
        text.append(f"➡️ <a href='https://french-tolls.undiscoveredlatitudes.com/#{hash}'>Open comparison map</a>")
        await reply.edit_text("\n".join(text), parse_mode="HTML")
    except Exception as e:
        logger.warning("Error: %r", e, exc_info=True)
        await reply.edit_text("Error calculating this route. I am very sorry for that 😞")


async def help_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await send_help(update.message)


async def send_help(message):
    await message.reply_text(
        f"This is a bot that will calculate a route within mainland France that uses toll roads but will not be too "
        f"expensive (it assumes an hour of driving time is worth 20 EUR).\n\n"

        "Just send the origin and the destination locations, and it will calculate the route.\n\n"

        "The full version is available here: https://french-tolls.undiscoveredlatitudes.com\n\n"

        "You can send me a tip using this link: https://paypal.me/themyloginspain"
    )


async def reset_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    users_from.pop(update.message.from_user.id, None)
    await update.message.reply_text("Now, send me the origin location")


async def post_init(application: Application):
    await application.bot.set_my_commands([
        ("help", "Help"),
        ("reset", "Reset the origin location"),
    ])


def main():
    application = (
        Application.
        builder().
        token(os.environ["TELEGRAM_BOT_TOKEN"]).
        post_init(post_init).
        build()
    )

    application.add_handler(MessageHandler((filters.TEXT | filters.LOCATION) & ~filters.COMMAND, text_message_handler))
    application.add_handler(CommandHandler("help", help_command_handler))
    application.add_handler(CommandHandler("reset", reset_command_handler))

    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG, format="[%(asctime)s] %(levelname)-8s [%(name)s] %(message)s")
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("telegram").setLevel(logging.WARNING)

    main()
