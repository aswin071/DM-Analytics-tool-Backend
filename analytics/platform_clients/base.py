"""
Base class for all social platform API clients.
Each platform must implement get_auth_url, exchange_code, and fetch_messages.
"""
from abc import ABC, abstractmethod


class BasePlatformClient(ABC):
    def __init__(self, platform_connection=None):
        self.connection = platform_connection

    @abstractmethod
    def get_auth_url(self, state=None):
        """Return the OAuth authorization URL for this platform."""
        pass

    @abstractmethod
    def exchange_code(self, code):
        """Exchange auth code for access token. Return dict with token info."""
        pass

    @abstractmethod
    def fetch_messages(self, since=None):
        """
        Fetch DMs from the platform API.
        Returns list of dicts:
        [
            {
                'platform_message_id': str,
                'conversation_id': str,
                'sender_id': str,
                'sender_name': str,
                'message_text': str,
                'direction': 'inbound' | 'outbound',
                'timestamp': datetime,
            },
            ...
        ]
        """
        pass

    def get_access_token(self):
        if self.connection:
            return self.connection.access_token
        return None
