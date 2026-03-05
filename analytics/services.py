"""
Business logic services: catalog import, DM sync, analytics.
"""
import csv
import io
from datetime import timedelta

from django.utils import timezone
from django.db.models import Count, Q

from .models import Product, DirectMessage, MessageClassification, CatalogUpload
from .classifier import classify_and_link
from .platform_clients import get_client


# ── Catalog Import ──

def import_catalog_csv(user, csv_file):
    """
    Import products from a CSV file.
    Expected columns: sku, name, category, price, keywords
    Returns (imported_count, failed_count, errors).
    """
    content = csv_file.read()
    if isinstance(content, bytes):
        content = content.decode('utf-8-sig')

    reader = csv.DictReader(io.StringIO(content))
    imported = 0
    failed = 0
    errors = []

    required_fields = {'sku', 'name'}
    if not required_fields.issubset(set(reader.fieldnames or [])):
        return 0, 0, [f"CSV must contain columns: {', '.join(required_fields)}"]

    for row_num, row in enumerate(reader, start=2):
        try:
            sku = row.get('sku', '').strip()
            name = row.get('name', '').strip()
            if not sku or not name:
                errors.append(f"Row {row_num}: sku and name are required")
                failed += 1
                continue

            price = None
            price_str = row.get('price', '').strip()
            if price_str:
                price = float(price_str.replace(',', ''))

            Product.objects.update_or_create(
                user=user,
                sku=sku,
                defaults={
                    'name': name,
                    'category': row.get('category', '').strip(),
                    'price': price,
                    'keywords': row.get('keywords', '').strip(),
                    'is_active': True,
                }
            )
            imported += 1
        except Exception as e:
            errors.append(f"Row {row_num}: {str(e)}")
            failed += 1

    # Track upload
    CatalogUpload.objects.create(
        user=user,
        file=csv_file,
        rows_imported=imported,
        rows_failed=failed,
    )

    return imported, failed, errors


# ── DM Sync ──

def sync_platform_messages(platform_connection):
    """
    Fetch new DMs from a platform and classify them.
    Returns count of new messages imported.
    """
    client = get_client(platform_connection)
    since = platform_connection.last_synced
    raw_messages = client.fetch_messages(since=since)

    count = 0
    for msg in raw_messages:
        dm, created = DirectMessage.objects.get_or_create(
            platform_message_id=msg['platform_message_id'],
            defaults={
                'user': platform_connection.user,
                'platform': platform_connection,
                'conversation_id': msg.get('conversation_id', ''),
                'sender_id': msg['sender_id'],
                'sender_name': msg.get('sender_name', ''),
                'message_text': msg.get('message_text', ''),
                'direction': msg.get('direction', 'inbound'),
                'timestamp': msg['timestamp'],
            }
        )
        if created:
            classify_and_link(dm)
            count += 1

    platform_connection.last_synced = timezone.now()
    platform_connection.save(update_fields=['last_synced'])
    return count


def sync_all_platforms(user):
    """Sync DMs from all connected platforms for a user."""
    from .models import SocialPlatform
    results = {}
    for conn in SocialPlatform.objects.filter(user=user, is_active=True):
        try:
            count = sync_platform_messages(conn)
            results[conn.platform] = {'synced': count, 'error': None}
        except Exception as e:
            results[conn.platform] = {'synced': 0, 'error': str(e)}
    return results


# ── Analytics Queries ──

def get_dm_stats(user, days=None):
    """Get DM volume stats for a user."""
    qs = DirectMessage.objects.filter(user=user, direction='inbound')

    now = timezone.now()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    stats = {
        'total': qs.count(),
        'today': qs.filter(timestamp__gte=today_start).count(),
        'this_week': qs.filter(timestamp__gte=now - timedelta(days=7)).count(),
        'this_month': qs.filter(timestamp__gte=now - timedelta(days=30)).count(),
        'unanswered': qs.filter(is_resolved=False).count(),
    }

    if days:
        stats['period'] = qs.filter(timestamp__gte=now - timedelta(days=days)).count()

    return stats


def get_top_products(user, limit=5, days=30):
    """Get most queried products."""
    since = timezone.now() - timedelta(days=days)
    return (
        Product.objects.filter(user=user, is_active=True)
        .annotate(
            mention_count=Count(
                'classifications',
                filter=Q(classifications__message__timestamp__gte=since)
            )
        )
        .order_by('-mention_count')[:limit]
    )


def get_category_breakdown(user, days=30):
    """Get query category breakdown for pie chart."""
    since = timezone.now() - timedelta(days=days)
    return (
        MessageClassification.objects.filter(
            message__user=user,
            message__direction='inbound',
            message__timestamp__gte=since,
        )
        .values('category')
        .annotate(count=Count('id'))
        .order_by('-count')
    )


def get_product_analytics(product, days=30):
    """Get detailed analytics for a single product."""
    since = timezone.now() - timedelta(days=days)
    classifications = MessageClassification.objects.filter(
        matched_products=product,
        message__timestamp__gte=since,
    )

    category_breakdown = (
        classifications.values('category')
        .annotate(count=Count('id'))
        .order_by('-count')
    )

    total = classifications.count()
    purchase_intent = classifications.filter(category='purchase_intent').count()

    return {
        'total_mentions': total,
        'category_breakdown': list(category_breakdown),
        'purchase_intent_score': round((purchase_intent / total * 100) if total else 0, 1),
        'recent_messages': classifications.select_related('message')[:20],
    }


def get_peak_hours(user, days=30):
    """Get DM volume by hour of day."""
    since = timezone.now() - timedelta(days=days)
    from django.db.models.functions import ExtractHour
    return (
        DirectMessage.objects.filter(
            user=user, direction='inbound', timestamp__gte=since
        )
        .annotate(hour=ExtractHour('timestamp'))
        .values('hour')
        .annotate(count=Count('id'))
        .order_by('hour')
    )


def get_daily_volume(user, days=30):
    """Get DM volume by day."""
    since = timezone.now() - timedelta(days=days)
    from django.db.models.functions import TruncDate
    return (
        DirectMessage.objects.filter(
            user=user, direction='inbound', timestamp__gte=since
        )
        .annotate(date=TruncDate('timestamp'))
        .values('date')
        .annotate(count=Count('id'))
        .order_by('date')
    )


def get_platform_breakdown(user, days=30):
    """Get DM count per platform."""
    since = timezone.now() - timedelta(days=days)
    return (
        DirectMessage.objects.filter(
            user=user, direction='inbound', timestamp__gte=since
        )
        .values('platform__platform')
        .annotate(count=Count('id'))
        .order_by('-count')
    )
