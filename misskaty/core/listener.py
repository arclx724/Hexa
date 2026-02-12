import asyncio
from contextlib import suppress
from typing import Optional

from pyrogram import Client, filters as pyro_filters
from pyrogram.handlers import CallbackQueryHandler, MessageHandler
from pyrogram.types import Chat, Message

from misskaty.core.listener_errors import ListenerTimeout, patch_pyrogram_errors

_UNALLOWED_CLICK_TEXT = "You're not expected to click this button."


async def _wait_for_future(future: asyncio.Future, timeout: Optional[float]):
    try:
        return await asyncio.wait_for(future, timeout)
    except asyncio.TimeoutError as exc:
        raise ListenerTimeout from exc


async def listen(
    self: Client,
    chat_id: int,
    filters=pyro_filters.all,
    timeout: Optional[float] = None,
    from_user_id: int = None,
):
    future = asyncio.get_running_loop().create_future()
    handler_filter = pyro_filters.incoming & filters

    if chat_id is not None:
        handler_filter = pyro_filters.chat(chat_id) & handler_filter
    if from_user_id is not None:
        handler_filter = pyro_filters.user(from_user_id) & handler_filter

    async def _on_message(_, message: Message):
        if not future.done():
            future.set_result(message)

    handler = MessageHandler(_on_message, handler_filter)
    group = -987654
    self.add_handler(handler, group)

    try:
        return await _wait_for_future(future, timeout)
    finally:
        with suppress(Exception):
            self.remove_handler(handler, group)


async def client_ask(
    self: Client,
    chat_id: int,
    text: str,
    filters=pyro_filters.text,
    timeout: Optional[float] = None,
    disable_web_page_preview=None,
    reply_to_message_id=None,
    reply_markup=None,
    from_user_id: int = None,
    **kwargs,
):
    sent = await self.send_message(
        chat_id=chat_id,
        text=text,
        disable_web_page_preview=disable_web_page_preview,
        reply_to_message_id=reply_to_message_id,
        reply_markup=reply_markup,
        **kwargs,
    )
    response = await self.listen(
        chat_id=chat_id,
        filters=filters,
        timeout=timeout,
        from_user_id=from_user_id,
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
    return await self._client.ask(
        chat_id=self.id,
        text=text,
        filters=filters,
        timeout=timeout,
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
        reply_to_message_id=self.id,
        **kwargs,
    )


async def wait_for_click(
    self: Message, from_user_id: int = None, timeout: Optional[float] = None
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
    group = -987653
    self._client.add_handler(handler, group)

    try:
        return await _wait_for_future(future, timeout)
    finally:
        with suppress(Exception):
            self._client.remove_handler(handler, group)


async def client_wait_for_click(
    self: Client, message: Message, from_user_id: int = None, timeout: Optional[float] = None
):
    return await message.wait_for_click(from_user_id=from_user_id, timeout=timeout)


def setup_listener_patch():
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
