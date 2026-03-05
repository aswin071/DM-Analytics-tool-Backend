from .instagram import InstagramClient
from .facebook import FacebookClient
from .twitter import TwitterClient
from .whatsapp import WhatsAppClient

PLATFORM_CLIENTS = {
    'instagram': InstagramClient,
    'facebook': FacebookClient,
    'twitter': TwitterClient,
    'whatsapp': WhatsAppClient,
}


def get_client(platform_connection):
    """Factory: return the right client for a SocialPlatform instance."""
    client_class = PLATFORM_CLIENTS.get(platform_connection.platform)
    if not client_class:
        raise ValueError(f"Unsupported platform: {platform_connection.platform}")
    return client_class(platform_connection)
