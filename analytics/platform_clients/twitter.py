"""Twitter/X API v2 client for DM fetching."""
import requests
import hashlib
import base64
import secrets
from datetime import datetime
from django.conf import settings
from django.utils import timezone
from .base import BasePlatformClient

TWITTER_AUTH_URL = 'https://twitter.com/i/oauth2/authorize'
TWITTER_TOKEN_URL = 'https://api.twitter.com/2/oauth2/token'
TWITTER_API_BASE = 'https://api.twitter.com/2'


class TwitterClient(BasePlatformClient):
    def get_auth_url(self, state=None):
        # Twitter uses PKCE OAuth 2.0
        code_verifier = secrets.token_urlsafe(64)
        code_challenge = base64.urlsafe_b64encode(
            hashlib.sha256(code_verifier.encode()).digest()
        ).rstrip(b'=').decode()

        params = {
            'response_type': 'code',
            'client_id': settings.TWITTER_API_KEY,
            'redirect_uri': settings.TWITTER_REDIRECT_URI,
            'scope': 'dm.read dm.write users.read tweet.read offline.access',
            'state': state or secrets.token_urlsafe(32),
            'code_challenge': code_challenge,
            'code_challenge_method': 'S256',
        }
        qs = '&'.join(f'{k}={v}' for k, v in params.items())
        # Store code_verifier in session (caller must handle this)
        self._code_verifier = code_verifier
        return f'{TWITTER_AUTH_URL}?{qs}'

    def exchange_code(self, code, code_verifier=None):
        resp = requests.post(TWITTER_TOKEN_URL, data={
            'grant_type': 'authorization_code',
            'code': code,
            'redirect_uri': settings.TWITTER_REDIRECT_URI,
            'client_id': settings.TWITTER_API_KEY,
            'code_verifier': code_verifier or '',
        }, auth=(settings.TWITTER_API_KEY, settings.TWITTER_API_SECRET), timeout=30)
        resp.raise_for_status()
        data = resp.json()

        # Get user info
        user_resp = requests.get(f'{TWITTER_API_BASE}/users/me', headers={
            'Authorization': f'Bearer {data["access_token"]}',
        }, timeout=30)
        user_resp.raise_for_status()
        user_data = user_resp.json().get('data', {})

        expires_in = data.get('expires_in', 7200)
        return {
            'access_token': data['access_token'],
            'refresh_token': data.get('refresh_token', ''),
            'platform_user_id': user_data.get('id', ''),
            'page_id': '',
            'username': user_data.get('username', ''),
            'expires_at': timezone.now() + timezone.timedelta(seconds=expires_in),
        }

    def fetch_messages(self, since=None):
        token = self.get_access_token()
        headers = {'Authorization': f'Bearer {token}'}

        params = {
            'dm_event.fields': 'id,text,sender_id,created_at,dm_conversation_id',
            'max_results': 100,
        }

        resp = requests.get(f'{TWITTER_API_BASE}/dm_events', headers=headers, params=params, timeout=30)
        resp.raise_for_status()
        events = resp.json().get('data', [])

        messages = []
        for event in events:
            ts = datetime.strptime(event['created_at'], '%Y-%m-%dT%H:%M:%S.%fZ').replace(
                tzinfo=timezone.utc
            )
            if since and ts < since:
                continue

            is_own = event.get('sender_id') == self.connection.platform_user_id

            messages.append({
                'platform_message_id': event['id'],
                'conversation_id': event.get('dm_conversation_id', ''),
                'sender_id': event.get('sender_id', ''),
                'sender_name': '',  # Would need user lookup
                'message_text': event.get('text', ''),
                'direction': 'outbound' if is_own else 'inbound',
                'timestamp': ts,
            })

        return messages
