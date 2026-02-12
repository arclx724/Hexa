from __future__ import annotations

import asyncio
from contextlib import suppress
from logging import getLogger
from typing import Dict, Optional, Tuple

from pyrogram import Client, filters as pyro_filters
from pyrogram import types as pyro_types
from pyrogram.handlers import CallbackQueryHandler, MessageHandler
from pyrogram.types import Chat, Message

from misskaty.core.listener_errors import ListenerTimeout, patch_pyrogram_errors

_UNALLOWED_CLICK_TEXT = "You're not expected to click this button."
LOGGER = getLogger("MissKaty")
_ANY_USER = 0


class ConversationManager:
    def __init__(self):
        self._futures: Dict[Tuple[int, int], Tuple[asyncio.Future, object]] = {}
        self._handler: Optional[MessageHandler] = None

    def register(self, client: Client):
        if self._handler is not None:
            return
        self._handler = MessageHandler(self._on_message, pyro_filters.incoming)
        client.add_handler(self._handler, group=-1)
        LOGGER.info("Conversation handler registered")

    async def _on_message(self, _, message: Message):
        if not message.from_user:
            return

        exact_key = (message.chat.id, message.from_user.id)
        any_key = (message.chat.id, _ANY_USER)

        key = exact_key if exact_key in self._futures else any_key
        if key not in self._futures:
            return

        future, flt = self._futures[key]

        if flt is not None:
            passed = flt.__call__(_, message)
            if asyncio.iscoroutine(passed):
                passed = await passed
            if not passed:
                return

        if not future.done():
            future.set_result(message)

    async def wait(
        self,
        chat_id: int,
        from_user_id: Optional[int],
        flt,
        timeout: Optional[float],
    ) -> Message:
        key = (chat_id, from_user_id if from_user_id is not None else _ANY_USER)
        existing = self._futures.get(key)
        if existing is not None:
            existing_future, _ = existing
            if existing_future.done() or existing_future.cancelled():
                self._futures.pop(key, None)
            else:
                raise ListenerTimeout(
                    "Another conversation is already running for this target"
                )

        future = asyncio.get_running_loop().create_future()
        self._futures[key] = (future, flt)
        try:
            return await asyncio.wait_for(future, timeout)
        except asyncio.TimeoutError as exc:
            raise ListenerTimeout from exc
        finally:
            self._futures.pop(key, None)


_CONVERSATION_MANAGER = ConversationManager()


async def listen(
    self: Client,
    chat_id: int,
    filters=pyro_filters.all,
    timeout: Optional[float] = None,
    from_user_id: int = None,
):
    return await _CONVERSATION_MANAGER.wait(chat_id, from_user_id, filters, timeout)


async def client_ask(
    self: Client,
    chat_id: int,
    text: str,
    filters=pyro_filters.text,
    timeout: Optional[float] = None,
    link_preview_options: Optional[pyro_types.LinkPreviewOptions] = None,
    reply_parameters: Optional[pyro_types.ReplyParameters] = None,
    reply_markup=None,
    from_user_id: int = None,
    **kwargs,
):
    listener_task = asyncio.create_task(
        self.listen(
            chat_id=chat_id,
            filters=filters,
            timeout=timeout,
            from_user_id=from_user_id,
        )
    )

    sent = await self.send_message(
        chat_id=chat_id,
        text=text,
        link_preview_options=link_preview_options,
        reply_parameters=reply_parameters,
        reply_markup=reply_markup,
        **kwargs,
    )

    response = await listener_task
    response.reply_to_message = sent
    return response


async def chat_ask(
    self: Chat,
    text: str,
    filters=pyro_filters.text,
    timeout: Optional[float] = None,
    **kwargs,
):
    from_user_id = kwargs.pop("from_user_id", None)

    return await self._client.ask(
        chat_id=self.id,
        text=text,
        filters=filters,
        timeout=timeout,
        from_user_id=from_user_id,
        **kwargs,
    )


async def message_ask(
    self: Message,
    text: str,
    filters=pyro_filters.text,
    timeout: Optional[float] = None,
    **kwargs,
):
    from_user_id = kwargs.pop("from_user_id", None)
    if from_user_id is None and self.from_user:
        from_user_id = self.from_user.id

    return await self._client.ask(
        chat_id=self.chat.id,
        text=text,
        filters=filters,
        timeout=timeout,
        from_user_id=from_user_id,
        reply_parameters=pyro_types.ReplyParameters(message_id=self.id),
        **kwargs,
    )


async def wait_for_click(
    self: Message,
    from_user_id: int = None,
    timeout: Optional[float] = None,
    expired_message: Optional[str] = "⚠️ Task expired.",
):
    future = asyncio.get_running_loop().create_future()

    async def _on_callback(_, query):
        if query.message.chat.id != self.chat.id or query.message.id != self.id:
            return

        if (
            from_user_id is not None
            and query.from_user
            and query.from_user.id != from_user_id
        ):
            with suppress(Exception):
                await query.answer(_UNALLOWED_CLICK_TEXT, show_alert=True)
            return

        if not future.done():
            future.set_result(query)

    handler = CallbackQueryHandler(_on_callback)
    group = -2
    self._client.add_handler(handler, group)

    try:
        return await asyncio.wait_for(future, timeout)
    except asyncio.TimeoutError as exc:
        if expired_message:
            with suppress(Exception):
                await self.edit_text(expired_message)
        raise ListenerTimeout from exc
    finally:
        with suppress(Exception):
            self._client.remove_handler(handler, group)


async def client_wait_for_click(
    self: Client,
    message: Message,
    from_user_id: int = None,
    timeout: Optional[float] = None,
):
    return await message.wait_for_click(from_user_id=from_user_id, timeout=timeout)


def setup_listener_patch(client: Optional[Client] = None):
    patch_pyrogram_errors()
    Client.listen = listen
    Client.ask = client_ask
    Client.wait_for_click = client_wait_for_click
    Chat.ask = chat_ask
    Message.ask = message_ask
    Message.wait_for_click = wait_for_click

    if client is not None:
        _CONVERSATION_MANAGER.register(client)


__all__ = [
    "setup_listener_patch",
    "listen",
    "client_ask",
    "chat_ask",
    "message_ask",
    "wait_for_click",
    "client_wait_for_click",
]
