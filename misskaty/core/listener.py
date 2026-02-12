from __future__ import annotations

import asyncio
from contextlib import suppress
from logging import getLogger
from typing import Optional

from pyrogram import Client, filters as pyro_filters
from pyrogram import types as pyro_types
from pyrogram.handlers import CallbackQueryHandler, MessageHandler
from pyrogram.types import Chat, Message

from misskaty.core.listener_errors import ListenerTimeout, patch_pyrogram_errors

_UNALLOWED_CLICK_TEXT = "You're not expected to click this button."
LOGGER = getLogger("MissKaty")


async def listen(
    self: Client,
    chat_id: int,
    filters=pyro_filters.all,
    timeout: Optional[float] = None,
    from_user_id: int = None,
):
    future = asyncio.get_running_loop().create_future()

    handler_filter = pyro_filters.incoming & pyro_filters.chat(chat_id) & filters
    if from_user_id is not None:
        handler_filter = handler_filter & pyro_filters.user(from_user_id)

    async def _on_message(_, message: Message):
        if not future.done():
            future.set_result(message)

    handler = MessageHandler(_on_message, handler_filter)
    group = -999999
    self.add_handler(handler, group)

    try:
        return await asyncio.wait_for(future, timeout)
    except asyncio.TimeoutError as exc:
        raise ListenerTimeout from exc
    finally:
        with suppress(Exception):
            self.remove_handler(handler, group)


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
    LOGGER.debug(
        "ask() register listener chat_id=%s from_user_id=%s timeout=%s",
        chat_id,
        from_user_id,
        timeout,
    )
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
    LOGGER.debug(
        "ask() got response chat_id=%s user_id=%s msg_id=%s",
        response.chat.id if response.chat else None,
        response.from_user.id if response.from_user else None,
        response.id,
    )
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
    group = -999998
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


__all__ = [
    "setup_listener_patch",
    "listen",
    "client_ask",
    "chat_ask",
    "message_ask",
    "wait_for_click",
    "client_wait_for_click",
]
