from functools import partial
from asyncio import create_task, sleep
from typing import Union

from pyrogram import filters
from pyrogram.enums import ChatType
from pyrogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from database.locale_db import set_db_lang
from misskaty import app
from misskaty.vars import COMMAND_HANDLER

from ..core.decorator.permissions import require_admin
from ..helper.localization import (
    default_language,
    get_locale_string,
    langdict,
    use_chat_lang,
)


LANG_TIMEOUT = 30
pending_lang_sessions = {}


async def expire_lang_session(message_id, strings):
    await sleep(LANG_TIMEOUT)
    session = pending_lang_sessions.get(message_id)
    if not session or not session.get("active"):
        return
    session["active"] = False
    try:
        await app.edit_message_text(
            chat_id=session["chat_id"],
            message_id=message_id,
            text=strings("exp_task", context="general"),
        )
    except Exception:
        pass
    pending_lang_sessions.pop(message_id, None)


def gen_langs_kb():
    langs = list(langdict)
    kb = []
    while langs:
        lang = langdict[langs[0]]["main"]
        a = [
            InlineKeyboardButton(
                f"{lang['language_flag']} {lang['language_name']}",
                callback_data=f"set_lang {langs[0]}",
            )
        ]

        langs.pop(0)
        if langs:
            lang = langdict[langs[0]]["main"]
            a.append(
                InlineKeyboardButton(
                    f"{lang['language_flag']} {lang['language_name']}",
                    callback_data=f"set_lang {langs[0]}",
                )
            )

            langs.pop(0)
        kb.append(a)
    return kb


@app.on_callback_query(filters.regex("^chlang$"))
@app.on_message(filters.command(["setchatlang", "setlang"], COMMAND_HANDLER))
@require_admin(allow_in_private=True)
@use_chat_lang()
async def chlang(_, m: Union[CallbackQuery, Message], strings):
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            *gen_langs_kb(),
            [
                InlineKeyboardButton(
                    strings("back_btn", context="general"), callback_data="start_back"
                )
            ],
        ]
    )

    if isinstance(m, CallbackQuery):
        msg = m.message
        sender = msg.edit_text
    else:
        msg = m
        sender = msg.reply_text
        if not msg.from_user:
            return

    res = (
        strings("language_changer_private")
        if msg.chat.type == ChatType.PRIVATE
        else strings("language_changer_chat")
    )
    sent_msg = await sender(res, reply_markup=keyboard)
    pending_lang_sessions[sent_msg.id] = {
        "chat_id": sent_msg.chat.id,
        "user_id": m.from_user.id,
        "active": True,
        "timeout_task": create_task(expire_lang_session(sent_msg.id, strings)),
    }


@app.on_callback_query(filters.regex("^set_lang "))
@require_admin(allow_in_private=True)
@use_chat_lang()
async def set_chat_lang(_, m: CallbackQuery, strings):
    session = pending_lang_sessions.get(m.message.id)
    if not session or not session.get("active"):
        return await m.answer(strings("exp_task", context="general"), show_alert=True)
    if m.from_user.id != session["user_id"]:
        return await m.answer("Hanya user yang membuka menu ini yang bisa memilih bahasa.", show_alert=True)

    session["active"] = False
    timeout_task = session.get("timeout_task")
    if timeout_task and not timeout_task.done():
        timeout_task.cancel()
    pending_lang_sessions.pop(m.message.id, None)

    lang = m.data.split()[1]
    await set_db_lang(m.message.chat.id, m.message.chat.type, lang)

    strings = partial(
        get_locale_string,
        langdict[lang].get("lang_setting", langdict[default_language]["lang_setting"]),
        lang,
        "lang_setting",
    )

    if m.message.chat.type == ChatType.PRIVATE:
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        strings("back_btn", context="general"),
                        callback_data="start_back",
                    )
                ]
            ]
        )
    else:
        keyboard = None
    await m.message.edit(
        strings("language_changed_successfully"), reply_markup=keyboard
    )
