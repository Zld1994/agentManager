"""Backward-compatible alias for profile memory."""

from .profile_memory import ProfileMemory


class SessionMemory(ProfileMemory):
    """Backward-compatible session layer built on ProfileMemory."""
