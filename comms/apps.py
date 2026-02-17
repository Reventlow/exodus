"""Comms app configuration."""

from django.apps import AppConfig


class CommsConfig(AppConfig):
    """Configuration for the comms (in-game messaging) application."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "comms"
    verbose_name = "Comms"
