from __future__ import annotations

import inspect
from functools import lru_cache
from typing import Any

from pyrogram.types import ChatPermissions


PERMISSION_ALIASES = {
    "can_send_docs": "can_send_documents",
    "can_send_voices": "can_send_voice_notes",
    "can_send_roundvideos": "can_send_video_notes",
    "can_send_plain": "can_send_messages",
    "can_send_gifs": "can_send_other_messages",
    "can_send_games": "can_send_other_messages",
    "can_send_inline": "can_send_other_messages",
    "can_send_stickers": "can_send_other_messages",
}


@lru_cache(maxsize=1)
def available_permission_fields() -> set[str]:
    signature = inspect.signature(ChatPermissions.__init__)
    return {
        name
        for name in signature.parameters
        if name not in {"self", "kwargs", "all_perms"}
    }


def _read_perm_value(perm_obj: Any, key: str) -> Any:
    if isinstance(perm_obj, dict):
        if key in perm_obj:
            return perm_obj[key]
        alias = PERMISSION_ALIASES.get(key)
        if alias and alias in perm_obj:
            return perm_obj[alias]
        for legacy, current in PERMISSION_ALIASES.items():
            if current == key and legacy in perm_obj:
                return perm_obj[legacy]
        return None

    if hasattr(perm_obj, key):
        return getattr(perm_obj, key)

    alias = PERMISSION_ALIASES.get(key)
    if alias and hasattr(perm_obj, alias):
        return getattr(perm_obj, alias)

    for legacy, current in PERMISSION_ALIASES.items():
        if current == key and hasattr(perm_obj, legacy):
            return getattr(perm_obj, legacy)

    return None


def export_permissions(perm_obj: Any) -> dict[str, bool]:
    data: dict[str, bool] = {}
    for field in available_permission_fields():
        value = _read_perm_value(perm_obj, field)
        if value is None:
            continue
        data[field] = bool(value)
    return data


def build_chat_permissions(perm_obj: Any = None, **overrides: bool) -> ChatPermissions:
    data = export_permissions(perm_obj) if perm_obj is not None else {}
    data.update({k: v for k, v in overrides.items() if k in available_permission_fields()})
    return ChatPermissions(**data)


def empty_chat_permissions() -> ChatPermissions:
    return build_chat_permissions(
        **{field: False for field in available_permission_fields()},
    )


def full_chat_permissions() -> ChatPermissions:
    return build_chat_permissions(
        **{field: True for field in available_permission_fields()},
    )

