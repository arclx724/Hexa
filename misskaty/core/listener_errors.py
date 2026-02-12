from pyrogram import errors as pyrogram_errors


class ListenerTimeout(Exception):
    """Raised when a listener did not receive an update in the allotted timeout."""


def patch_pyrogram_errors():
    if not hasattr(pyrogram_errors, "ListenerTimeout"):
        pyrogram_errors.ListenerTimeout = ListenerTimeout


__all__ = ["ListenerTimeout", "patch_pyrogram_errors"]
