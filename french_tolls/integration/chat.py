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


def labelled(call, label):
    """The callback data of the button labelled `label` in a call, or None."""
    for row in (call.markup or {}).get("inline_keyboard", []):
        for button in row:
            if button["text"] == label:
                return button["callback_data"]
    return None


def driving_buttons(call):
    """The callback data of the buttons of a call, without `Plan refuel`."""
    return [button["callback_data"] for row in (call.markup or {}).get("inline_keyboard", []) for button in row
            if button["text"] != "Plan refuel"]


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
                "message": self._pressed_message(message_id or next(self._updates)),
            },
        })

    def _pressed_message(self, message_id):
        """The message as the bot sent it: a press on a photo must arrive on a photo."""
        message = {
            "message_id": message_id,
            "date": 0,
            "chat": {"id": CHAT_ID, "type": "private"},
            "from": {"id": 424242, "is_bot": True, "first_name": "French Tolls"},
            "text": "the message the button was on",
        }
        sent = [s for s in self.telegram.sent if s.message_id == message_id and s.method == "sendPhoto"]
        if sent:
            del message["text"]
            message["photo"] = [{"file_id": "gauges", "file_unique_id": "gauges", "width": 1200, "height": 400}]
            message["caption"] = sent[0].text
        return message

    async def press_offered(self, choice=None):
        """Press a button offered since the last press. False if none was.

        Since the last press, not anywhere in the transcript. The flow retires a
        button by editing the markup away, but the call that offered it is still
        recorded, and looking at all of them would press the same button for ever.

        An offer is any call that carries buttons, an edit of the markup alone
        included: that is how "Drive with Google" follows a choice of route.

        The latest offer's button labelled `choice` is pressed where it has one,
        and its last button otherwise. `Plan refuel` is a way not to drive yet,
        so it is pressed only where `choice` names it.
        """
        fresh = self.telegram.sent[self._pressed_at:]
        offers = [call for call in fresh if driving_buttons(call) or labelled(call, choice)]
        if not offers:
            return False
        self._pressed_at = len(self.telegram.sent)
        latest = offers[-1]
        token = labelled(latest, choice) or driving_buttons(latest)[-1]
        await self.press(token, latest.message_id)
        return True

    async def press_labelled(self, label):
        for message in reversed(self.telegram.messages):
            token = labelled(message, label)
            if token is not None:
                await self.press(token, message.message_id)
                return
        raise AssertionError(f"no message offers a button labelled {label!r}")

    async def drive(self, origin, destination, presses=8, choice=None):
        """A whole journey: both locations, then every part it owes.

        `presses` bounds the loop rather than describing the journey. A flow that
        offered a button forever would otherwise hang a test instead of failing.

        `choice` is the label of the route to press where the answer offers a choice,
        and `Optimal` where it names none.
        """
        await self.send_location(origin)
        await self.send_location(destination)
        for _ in range(presses):
            if not await self.press_offered(choice or "Optimal"):
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
