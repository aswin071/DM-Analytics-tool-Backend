"""WhatsApp Business API client for message fetching."""
import requests
from django.conf import settings
from django.utils import timezone
from .base import BasePlatformClient

GRAPH_API_BASE = 'https://graph.facebook.com/v18.0'


class WhatsAppClient(BasePlatformClient):
    def get_auth_url(self, state=None):
        # WhatsApp Business API uses direct token setup, not OAuth flow.
        # Users configure via Meta Business Manager and provide tokens directly.
        return None

    def exchange_code(self, code):
        # WhatsApp doesn't use OAuth code exchange.
        # Token is set directly from Meta Business Manager.
        return {}

    def fetch_messages(self, since=None):
        """
        WhatsApp Business API works via webhooks (push model).
        This method is a placeholder — messages are ingested via webhook endpoint.
        For polling, you'd use the WhatsApp Cloud API's messages endpoint.
        """
        # WhatsApp Cloud API doesn't have a "list all messages" endpoint.
        # Messages arrive via webhooks and are stored in the webhook handler.
        # This returns an empty list — see views.whatsapp_webhook for ingestion.
        return []

    @staticmethod
    def verify_webhook(request):
        """Verify WhatsApp webhook subscription."""
        mode = request.GET.get('hub.mode')
        token = request.GET.get('hub.verify_token')
        challenge = request.GET.get('hub.challenge')

        verify_token = settings.WHATSAPP_ACCESS_TOKEN[:20]  # Use first 20 chars as verify token
        if mode == 'subscribe' and token == verify_token:
            return challenge
        return None

    @staticmethod
    def parse_webhook_payload(payload):
        """
        Parse incoming WhatsApp webhook payload into message dicts.
        """
        messages = []
        for entry in payload.get('entry', []):
            for change in entry.get('changes', []):
                value = change.get('value', {})
                for msg in value.get('messages', []):
                    contact = next(
                        (c for c in value.get('contacts', []) if c.get('wa_id') == msg.get('from')),
                        {}
                    )
                    messages.append({
                        'platform_message_id': msg.get('id', ''),
                        'conversation_id': msg.get('from', ''),
                        'sender_id': msg.get('from', ''),
                        'sender_name': contact.get('profile', {}).get('name', ''),
                        'message_text': msg.get('text', {}).get('body', ''),
                        'direction': 'inbound',
                        'timestamp': timezone.datetime.fromtimestamp(
                            int(msg.get('timestamp', 0)), tz=timezone.utc
                        ),
                    })
        return messages
