from pyrogram import errors as pyrogram_errors


class ListenerTimeout(Exception):
    """Raised when a listener did not receive an update in the allotted timeout."""


class ConversationExist(Exception):
    """Raised when a conversation for the same (chat_id, user_id) already exists."""


class ConversationTimeout(ListenerTimeout):
    """Raised when conversation wait exceeded timeout."""


def patch_pyrogram_errors():
    if not hasattr(pyrogram_errors, "ListenerTimeout"):
        pyrogram_errors.ListenerTimeout = ListenerTimeout


__all__ = [
    "ListenerTimeout",
    "ConversationExist",
    "ConversationTimeout",
    "patch_pyrogram_errors",
]
