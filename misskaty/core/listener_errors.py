class ListenerTimeout(Exception):
    """Raised when a listener did not receive an update in the allotted timeout."""


__all__ = ["ListenerTimeout"]
