"""Outbound webhook transport adapters."""

from .http_client import HttpWebhookSender

__all__ = ["HttpWebhookSender"]
