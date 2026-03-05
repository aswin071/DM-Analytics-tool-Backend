"""Instagram Graph API client for DM fetching."""
import requests
from datetime import datetime
from django.conf import settings
from django.utils import timezone
from .base import BasePlatformClient

GRAPH_API_BASE = 'https://graph.facebook.com/v18.0'


class InstagramClient(BasePlatformClient):
    def get_auth_url(self, state=None):
        params = {
            'client_id': settings.META_APP_ID,
            'redirect_uri': settings.META_REDIRECT_URI,
            'scope': 'instagram_manage_messages,instagram_basic,pages_manage_metadata,pages_messaging',
            'response_type': 'code',
        }
        if state:
            params['state'] = state
        qs = '&'.join(f'{k}={v}' for k, v in params.items())
        return f'https://www.facebook.com/v18.0/dialog/oauth?{qs}'

    def exchange_code(self, code):
        resp = requests.get(f'{GRAPH_API_BASE}/oauth/access_token', params={
            'client_id': settings.META_APP_ID,
            'client_secret': settings.META_APP_SECRET,
            'redirect_uri': settings.META_REDIRECT_URI,
            'code': code,
        }, timeout=30)
        resp.raise_for_status()
        data = resp.json()

        # Exchange for long-lived token
        long_resp = requests.get(f'{GRAPH_API_BASE}/oauth/access_token', params={
            'grant_type': 'fb_exchange_token',
            'client_id': settings.META_APP_ID,
            'client_secret': settings.META_APP_SECRET,
            'fb_exchange_token': data['access_token'],
        }, timeout=30)
        long_resp.raise_for_status()
        long_data = long_resp.json()

        # Get Instagram Business Account ID via linked Page
        pages_resp = requests.get(f'{GRAPH_API_BASE}/me/accounts', params={
            'access_token': long_data['access_token'],
        }, timeout=30)
        pages_resp.raise_for_status()
        pages = pages_resp.json().get('data', [])

        ig_account_id = None
        page_id = None
        username = ''
        for page in pages:
            page_id = page['id']
            ig_resp = requests.get(f'{GRAPH_API_BASE}/{page_id}', params={
                'fields': 'instagram_business_account',
                'access_token': long_data['access_token'],
            }, timeout=30)
            ig_data = ig_resp.json()
            if 'instagram_business_account' in ig_data:
                ig_account_id = ig_data['instagram_business_account']['id']
                # Get username
                user_resp = requests.get(f'{GRAPH_API_BASE}/{ig_account_id}', params={
                    'fields': 'username',
                    'access_token': long_data['access_token'],
                }, timeout=30)
                username = user_resp.json().get('username', '')
                break

        expires_in = long_data.get('expires_in', 5184000)  # default 60 days
        return {
            'access_token': long_data['access_token'],
            'platform_user_id': ig_account_id or '',
            'page_id': page_id or '',
            'username': username,
            'expires_at': timezone.now() + timezone.timedelta(seconds=expires_in),
        }

    def fetch_messages(self, since=None):
        token = self.get_access_token()
        page_id = self.connection.page_id
        if not page_id:
            return []

        # Fetch conversations
        params = {
            'platform': 'instagram',
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
                    'sender_name': sender.get('name', sender.get('username', '')),
                    'message_text': msg_data.get('message', ''),
                    'direction': 'outbound' if is_own else 'inbound',
                    'timestamp': ts,
                })

        return messages
