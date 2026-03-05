"""Facebook Messenger API client for DM fetching."""
import requests
from datetime import datetime
from django.conf import settings
from django.utils import timezone
from .base import BasePlatformClient

GRAPH_API_BASE = 'https://graph.facebook.com/v18.0'


class FacebookClient(BasePlatformClient):
    def get_auth_url(self, state=None):
        params = {
            'client_id': settings.META_APP_ID,
            'redirect_uri': settings.META_REDIRECT_URI.replace('/instagram/', '/facebook/'),
            'scope': 'pages_messaging,pages_manage_metadata,pages_read_engagement',
            'response_type': 'code',
        }
        if state:
            params['state'] = state
        qs = '&'.join(f'{k}={v}' for k, v in params.items())
        return f'https://www.facebook.com/v18.0/dialog/oauth?{qs}'

    def exchange_code(self, code):
        redirect_uri = settings.META_REDIRECT_URI.replace('/instagram/', '/facebook/')
        resp = requests.get(f'{GRAPH_API_BASE}/oauth/access_token', params={
            'client_id': settings.META_APP_ID,
            'client_secret': settings.META_APP_SECRET,
            'redirect_uri': redirect_uri,
            'code': code,
        }, timeout=30)
        resp.raise_for_status()
        data = resp.json()

        # Get long-lived token
        long_resp = requests.get(f'{GRAPH_API_BASE}/oauth/access_token', params={
            'grant_type': 'fb_exchange_token',
            'client_id': settings.META_APP_ID,
            'client_secret': settings.META_APP_SECRET,
            'fb_exchange_token': data['access_token'],
        }, timeout=30)
        long_resp.raise_for_status()
        long_data = long_resp.json()

        # Get page info
        pages_resp = requests.get(f'{GRAPH_API_BASE}/me/accounts', params={
            'access_token': long_data['access_token'],
        }, timeout=30)
        pages_resp.raise_for_status()
        pages = pages_resp.json().get('data', [])

        page = pages[0] if pages else {}
        expires_in = long_data.get('expires_in', 5184000)

        return {
            'access_token': page.get('access_token', long_data['access_token']),
            'platform_user_id': page.get('id', ''),
            'page_id': page.get('id', ''),
            'username': page.get('name', ''),
            'expires_at': timezone.now() + timezone.timedelta(seconds=expires_in),
        }

    def fetch_messages(self, since=None):
        token = self.get_access_token()
        page_id = self.connection.page_id or self.connection.platform_user_id
        if not page_id:
            return []

        params = {
            'fields': 'participants,messages{message,from,created_time}',
            'access_token': token,
        }
        resp = requests.get(f'{GRAPH_API_BASE}/{page_id}/conversations', params=params, timeout=30)
        resp.raise_for_status()
        conversations = resp.json().get('data', [])

        messages = []
        for convo in conversations:
            convo_id = convo['id']
            for msg_data in convo.get('messages', {}).get('data', []):
                ts = datetime.strptime(msg_data['created_time'], '%Y-%m-%dT%H:%M:%S%z')
                if since and ts < since:
                    continue

                sender = msg_data.get('from', {})
                is_own = sender.get('id') == self.connection.platform_user_id

                messages.append({
                    'platform_message_id': msg_data['id'],
                    'conversation_id': convo_id,
                    'sender_id': sender.get('id', ''),
                    'sender_name': sender.get('name', ''),
                    'message_text': msg_data.get('message', ''),
                    'direction': 'outbound' if is_own else 'inbound',
                    'timestamp': ts,
                })

        return messages
