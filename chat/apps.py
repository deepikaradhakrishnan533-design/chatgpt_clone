"""Application configuration for the chat application."""

from django.apps import AppConfig


class ChatConfig(AppConfig):
    """Configure the chat application."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "chat"
