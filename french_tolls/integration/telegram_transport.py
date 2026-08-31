# -*- coding=utf-8 -*-
"""A Telegram that answers from written responses and keeps what it was told.

The seam is `telegram.request.BaseRequest`, the one object between the messaging
library and a socket. Replace it and the library above is untouched: `Message`,
`CallbackQuery` and every markup are its own, built from these payloads exactly
as they are built from Telegram's. Nothing above knows it is a test.

`telegram-drive-flow` forbids the alternative -- substituting an object for the
messaging library -- and it is right to. Substituting a `Bot` would fake
`reply_text`, `edit_text`, `delete` and the markup construction, which is most of
what the shell does; the test would then assert that the fakes were called.
"""
import json
import re

from telegram.request import BaseRequest

__all__ = ["DRIVE_LABELS", "Sent", "Telegram"]

# The words on the link in every part the flow sends. Written here rather than
# imported from `bot`, so that changing what a driver reads changes a test.
DRIVE_LABELS = (
    "Drive this route",
    "Drive the next part of the route",
    "Drive the final part of the route",
)

# What the flow calls. Anything else is a method this project does not use, and
# a test that reaches one should fail rather than be quietly answered.
ANSWERED = (
    "getMe",
    "setMyCommands",
    "sendMessage",
    "editMessageText",
    "editMessageReplyMarkup",
    "answerCallbackQuery",
    "deleteMessage",
)


class Sent:
    """One call the flow made, as a test reads it."""

    def __init__(self, method, parameters, message_id):
        self.method = method
        self.parameters = parameters
        self.message_id = message_id

    @property
    def text(self) -> str:
        return self.parameters.get("text") or ""

    @property
    def markup(self):
        return self.parameters.get("reply_markup")

    @property
    def buttons(self) -> list:
        """The callback data of every button offered, in order."""
        markup = self.markup or {}
        rows = markup.get("inline_keyboard") if isinstance(markup, dict) else None
        return [b["callback_data"] for row in (rows or []) for b in row]

    @property
    def links(self) -> list:
        """Every href in the message, in the order a driver would read them."""
        return re.findall(r"href='([^']*)'", self.text)

    def __repr__(self):
        return f"Sent({self.method}, {self.text[:60]!r}, buttons={self.buttons})"


class Telegram(BaseRequest):
    """A transport that answers the Bot API and records every call.

    One instance per application. `sent` is the transcript, in order, and is the
    assertion surface: what a driver would have seen, and which buttons they
    could have pressed.
    """

    def __init__(self, bot_username="french_tolls_test_bot"):
        self.sent = []
        self.username = bot_username
        self._message_id = 0

    async def initialize(self) -> None:
        pass

    async def shutdown(self) -> None:
        pass

    # --- the transcript -------------------------------------------------------

    @property
    def messages(self) -> list:
        """What a driver is left looking at, in the order it appeared.

        One entry per message, carrying its final text. The flow sends
        "Calculating route..." and then edits that same message into the answer,
        so counting the send and the edit separately would report two messages
        where a driver saw one change under their thumb.

        A message the flow deleted does not appear at all. "Checking with Google..."
        sent and removed once the answer is ready: on the screen for a second,
        and in no driver's memory.
        """
        deleted = {s.parameters.get("message_id") for s in self.sent
                   if s.method == "deleteMessage"}

        order, final = [], {}
        for s in self.sent:
            if s.method not in ("sendMessage", "editMessageText"):
                continue
            if s.message_id not in final:
                order.append(s.message_id)
            final[s.message_id] = s

        return [final[i] for i in order if i not in deleted]

    @property
    def parts(self) -> list:
        """The messages offering a link to drive -- what the journey resolved into.

        The answer message carries a link too, to the comparison map, and is not
        a part. The label is what tells them apart, and it is the same string
        a driver taps. Three labels, because a part of a split journey is not
        offered as "this route", and the last part is named as the last.
        """
        return [m for m in self.messages
                if any(label in m.text for label in DRIVE_LABELS)]

    def texts(self) -> list:
        return [s.text for s in self.messages]

    def last_buttons(self) -> list:
        for s in reversed(self.messages):
            if s.buttons:
                return s.buttons
        return []

    # --- answering ------------------------------------------------------------

    async def do_request(self, url, method, request_data=None, **_timeouts):
        endpoint = url.rsplit("/", 1)[-1]
        parameters = dict(request_data.parameters) if request_data else {}

        if endpoint not in ANSWERED:
            raise AssertionError(
                f"the flow called {endpoint}, which this transport does not answer. "
                f"Add it to ANSWERED once it is clear what it should return.")

        # An edit names the message it changes, so it is recorded under that id
        # rather than a new one; that is what lets a send and its edits collapse
        # into the one message a driver sees.
        self._message_id += 1
        message_id = parameters.get("message_id") or self._message_id
        self.sent.append(Sent(endpoint, parameters, message_id))

        return 200, json.dumps(
            {"ok": True, "result": self._result(endpoint, parameters, message_id)}).encode()

    def _result(self, endpoint, parameters, message_id):
        if endpoint == "getMe":
            # `Bot.initialize` reads this and caches it. Marked a bot, or the
            # library refuses to use it as one.
            return {
                "id": 424242, "is_bot": True, "first_name": "French Tolls",
                "username": self.username, "can_join_groups": False,
                "can_read_all_group_messages": False,
                "supports_inline_queries": False,
            }

        if endpoint in ("setMyCommands", "answerCallbackQuery", "deleteMessage"):
            return True

        # A message payload the library parses into a `Message` the flow can
        # reply to, edit and delete. `date` is 0 rather than a clock reading:
        # nothing in the flow looks at it, and a test that reads a clock is a
        # test that fails on a slow machine one day in a thousand.
        return {
            "message_id": message_id,
            "date": 0,
            "chat": {"id": parameters.get("chat_id", 1), "type": "private"},
            "from": {"id": 424242, "is_bot": True, "first_name": "French Tolls",
                     "username": self.username},
            "text": parameters.get("text", ""),
            **({"reply_markup": parameters["reply_markup"]}
               if parameters.get("reply_markup") else {}),
        }
