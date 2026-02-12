from . import bound, decorators, methods
from misskaty.core.listener import setup_listener_patch


def init_patch(client=None):
    setup_listener_patch(client)
