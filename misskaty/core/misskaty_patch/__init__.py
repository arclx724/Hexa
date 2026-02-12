from . import bound, decorators, methods
from pyrogram import enums
from pyrogram.types import InlineKeyboardButton

from misskaty.core.listener import setup_listener_patch


_ORIG_IKB_INIT = InlineKeyboardButton.__init__
_CLOSE_EMOJI_ID = 6037254263187443802


def _patch_close_button_style():
    if getattr(InlineKeyboardButton, "_misskaty_close_style_patched", False):
        return

    def _patched_init(self, *args, **kwargs):
        _ORIG_IKB_INIT(self, *args, **kwargs)

        callback_data = kwargs.get("callback_data")
        if callback_data is None and len(args) > 1:
            callback_data = args[1]

        if isinstance(callback_data, str) and callback_data.startswith("close#"):
            self.icon_custom_emoji_id = _CLOSE_EMOJI_ID
            button_style = getattr(enums, "ButtonStyle", None)
            self.style = (
                button_style.DANGER
                if button_style and hasattr(button_style, "DANGER")
                else "DANGER"
            )

    InlineKeyboardButton.__init__ = _patched_init
    InlineKeyboardButton._misskaty_close_style_patched = True


def init_patch(client=None):
    _patch_close_button_style()
    setup_listener_patch(client)
