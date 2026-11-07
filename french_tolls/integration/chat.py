# -*- coding=utf-8 -*-
"""Driving the bot the way a driver drives it: updates in, transcript out."""
import itertools

from telegram import Update

from ..bot import build
from .telegram_transport import Telegram

__all__ = ["Chat"]

TOKEN = "424242:this-token-authenticates-nothing"
USER_ID = 777001
CHAT_ID = 777001


class Chat:
    """One driver, one application, and everything it was sent.

    Nothing here constructs a part, a token or a decision. A test sends the two
    locations a driver sends and presses the button the bot offered, because the
    handlers, the tokens and the message order are exactly what is untested
    everywhere else.
    """

    def __init__(self):
        self.telegram = Telegram()
        self.application = build(TOKEN, request=self.telegram,
                                 get_updates_request=self.telegram)
        self._updates = itertools.count(1)
        # How much of the transcript has already been answered by a press.
        self._pressed_at = 0
        # Every token pressed, in order. A test asserts these came from the bot.
        self.pressed = []

    async def __aenter__(self):
        await self.application.initialize()
        return self

    async def __aexit__(self, *_exc):
        await self.application.shutdown()
        return False

    # --- what a driver does ---------------------------------------------------

    async def send_location(self, lonlat):
        """Share a location, which is what a driver on a phone actually does."""
        lon, lat = lonlat
        await self._message({"location": {"longitude": lon, "latitude": lat}})

    async def send_text(self, text):
        """Type a message. Used for the help path; a location comes as a location.

        Worth knowing: `bot.parse_location` reads `lat, lon` from text with a
        regex that admits no minus sign, so a destination anywhere west of
        Greenwich cannot be typed. Every journey here is west of it. Not this
        change's to fix, and the reason the suite shares locations instead.
        """
        await self._message({"text": text})

    async def send_command(self, command):
        await self._message({
            "text": f"/{command}",
            "entities": [{"type": "bot_command", "offset": 0, "length": len(command) + 1}],
        })

    async def _message(self, body):
        await self._feed({
            "message": {
                "message_id": next(self._updates),
                "date": 0,
                "chat": {"id": CHAT_ID, "type": "private"},
                "from": {"id": USER_ID, "is_bot": False, "first_name": "Driver"},
                **body,
            },
        })

    async def press(self, token, message_id=None):
        """Press a button, by the callback data the bot itself put in it."""
        self.pressed.append(token)
        await self._feed({
            "callback_query": {
                "id": str(next(self._updates)),
                "from": {"id": USER_ID, "is_bot": False, "first_name": "Driver"},
                "chat_instance": "1",
                "data": token,
                "message": {
                    "message_id": message_id or next(self._updates),
                    "date": 0,
                    "chat": {"id": CHAT_ID, "type": "private"},
                    "from": {"id": 424242, "is_bot": True, "first_name": "French Tolls"},
                    "text": "the message the button was on",
                },
            },
        })

    async def press_offered(self):
        """Press a button offered since the last press. False if none was.

        Since the last press, not anywhere in the transcript. The flow retires a
        button by editing the markup away, and that edit is not a message a
        driver sees -- so the message carrying the spent button is still in the
        transcript, and looking at the whole of it would press the same button
        for ever.
        """
        fresh = self.telegram.messages[self._pressed_at:]
        buttons = [b for message in fresh for b in message.buttons]
        if not buttons:
            return False
        self._pressed_at = len(self.telegram.messages)
        await self.press(buttons[-1])
        return True

    async def press_labelled(self, label):
        for message in reversed(self.telegram.messages):
            for row in (message.markup or {}).get("inline_keyboard", []):
                for button in row:
                    if button["text"] == label:
                        await self.press(button["callback_data"], message.message_id)
                        return
        raise AssertionError(f"no message offers a button labelled {label!r}")

    async def drive(self, origin, destination, presses=8):
        """A whole journey: both locations, then every part it owes.

        `presses` bounds the loop rather than describing the journey. A flow that
        offered a button forever would otherwise hang a test instead of failing.
        """
        await self.send_location(origin)
        await self.send_location(destination)
        for _ in range(presses):
            if not await self.press_offered():
                return
        raise AssertionError(f"still offering a button after {presses} presses")

    async def _feed(self, payload):
        update = Update.de_json({"update_id": next(self._updates), **payload},
                                self.application.bot)
        await self.application.process_update(update)

    # --- what came back -------------------------------------------------------

    @property
    def sent(self):
        return self.telegram.sent

    @property
    def messages(self):
        return self.telegram.messages

    @property
    def parts(self):
        return self.telegram.parts

    def texts(self):
        return self.telegram.texts()
