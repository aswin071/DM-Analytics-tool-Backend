"""Management command to sync DMs from all connected platforms."""
from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from analytics.services import sync_all_platforms


class Command(BaseCommand):
    help = 'Sync DMs from all connected social platforms for all users (or a specific user)'

    def add_arguments(self, parser):
        parser.add_argument('--user', type=str, help='Username to sync (default: all users)')

    def handle(self, *args, **options):
        username = options.get('user')

        if username:
            users = User.objects.filter(username=username)
            if not users.exists():
                self.stderr.write(f'User "{username}" not found.')
                return
        else:
            users = User.objects.filter(platforms__is_active=True).distinct()

        for user in users:
            self.stdout.write(f'Syncing DMs for {user.username}...')
            results = sync_all_platforms(user)
            for platform, result in results.items():
                if result['error']:
                    self.stderr.write(f'  {platform}: ERROR — {result["error"]}')
                else:
                    self.stdout.write(f'  {platform}: {result["synced"]} new messages')

        self.stdout.write(self.style.SUCCESS('Sync complete.'))
