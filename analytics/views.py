import json
import csv

from rest_framework import viewsets, generics, status, filters
from rest_framework.decorators import api_view, permission_classes, action
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.pagination import PageNumberPagination
from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.shortcuts import get_object_or_404
from django_filters.rest_framework import DjangoFilterBackend

from .models import SocialPlatform, Product, DirectMessage, MessageClassification, CatalogUpload
from .serializers import (
    RegisterSerializer, UserSerializer, SocialPlatformSerializer,
    WhatsAppSetupSerializer, ProductSerializer, DirectMessageSerializer,
    CatalogUploadSerializer, DashboardStatsSerializer,
)
from .services import (
    import_catalog_csv, sync_all_platforms, sync_platform_messages,
    get_dm_stats, get_top_products, get_category_breakdown,
    get_product_analytics, get_peak_hours, get_daily_volume,
    get_platform_breakdown,
)
from .platform_clients import get_client, PLATFORM_CLIENTS


# ── Auth ──

class RegisterView(generics.CreateAPIView):
    serializer_class = RegisterSerializer
    permission_classes = [AllowAny]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        return Response(
            {'id': user.id, 'username': user.username, 'email': user.email},
            status=status.HTTP_201_CREATED,
        )


@api_view(['GET'])
def me_view(request):
    return Response(UserSerializer(request.user).data)


# ── Platform Connections ──

class PlatformListView(generics.ListAPIView):
    serializer_class = SocialPlatformSerializer

    def get_queryset(self):
        return SocialPlatform.objects.filter(user=self.request.user)


@api_view(['GET'])
def available_platforms(request):
    connected = set(
        SocialPlatform.objects.filter(user=request.user, is_active=True)
        .values_list('platform', flat=True)
    )
    platforms = []
    for key, display in SocialPlatform.PLATFORM_CHOICES:
        platforms.append({
            'key': key,
            'name': display,
            'connected': key in connected,
            'oauth_supported': key != 'whatsapp',
        })
    return Response(platforms)


@api_view(['GET'])
def connect_platform_url(request, platform):
    if platform not in PLATFORM_CLIENTS:
        return Response({'error': f'Unsupported platform: {platform}'}, status=400)

    client_class = PLATFORM_CLIENTS[platform]
    client = client_class()
    auth_url = client.get_auth_url(state=str(request.user.id))

    if not auth_url:
        return Response({'error': f'{platform} does not support OAuth. Use manual setup.'}, status=400)

    response_data = {'auth_url': auth_url}
    if hasattr(client, '_code_verifier'):
        # Client needs to store this for PKCE flow (Twitter)
        response_data['code_verifier'] = client._code_verifier

    return Response(response_data)


@api_view(['POST'])
def platform_callback(request, platform):
    code = request.data.get('code')
    if not code:
        return Response({'error': 'Authorization code is required.'}, status=400)

    client_class = PLATFORM_CLIENTS.get(platform)
    if not client_class:
        return Response({'error': f'Unsupported platform: {platform}'}, status=400)

    client = client_class()
    try:
        kwargs = {}
        if platform == 'twitter':
            kwargs['code_verifier'] = request.data.get('code_verifier', '')

        token_data = client.exchange_code(code, **kwargs)

        connection, created = SocialPlatform.objects.update_or_create(
            user=request.user,
            platform=platform,
            platform_user_id=token_data.get('platform_user_id', ''),
            defaults={
                'page_id': token_data.get('page_id', ''),
                'username': token_data.get('username', ''),
                'access_token': token_data['access_token'],
                'token_expires_at': token_data.get('expires_at'),
                'is_active': True,
            }
        )
        return Response(
            SocialPlatformSerializer(connection).data,
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )
    except Exception as e:
        return Response({'error': f'Failed to connect: {str(e)}'}, status=400)


@api_view(['POST'])
def setup_whatsapp(request):
    serializer = WhatsAppSetupSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    connection, _ = SocialPlatform.objects.update_or_create(
        user=request.user,
        platform='whatsapp',
        platform_user_id=serializer.validated_data['phone_number_id'],
        defaults={
            'access_token': serializer.validated_data['access_token'],
            'username': f"WhatsApp ({serializer.validated_data['phone_number_id']})",
            'is_active': True,
        }
    )
    return Response(SocialPlatformSerializer(connection).data, status=status.HTTP_201_CREATED)


@api_view(['POST'])
def disconnect_platform(request, pk):
    connection = get_object_or_404(SocialPlatform, pk=pk, user=request.user)
    connection.is_active = False
    connection.save(update_fields=['is_active'])
    return Response({'status': 'disconnected'})


@api_view(['POST'])
def reconnect_platform(request, pk):
    connection = get_object_or_404(SocialPlatform, pk=pk, user=request.user)
    connection.is_active = True
    connection.save(update_fields=['is_active'])
    return Response(SocialPlatformSerializer(connection).data)


# ── WhatsApp Webhook ──

@csrf_exempt
@api_view(['GET', 'POST'])
@permission_classes([AllowAny])
def whatsapp_webhook(request):
    from .platform_clients.whatsapp import WhatsAppClient

    if request.method == 'GET':
        challenge = WhatsAppClient.verify_webhook(request)
        if challenge:
            return HttpResponse(challenge)
        return Response({'error': 'Verification failed'}, status=403)

    try:
        payload = request.data if isinstance(request.data, dict) else json.loads(request.body)
        raw_messages = WhatsAppClient.parse_webhook_payload(payload)

        for msg in raw_messages:
            connections = SocialPlatform.objects.filter(platform='whatsapp', is_active=True)
            for conn in connections:
                dm, created = DirectMessage.objects.get_or_create(
                    platform_message_id=msg['platform_message_id'],
                    defaults={
                        'user': conn.user,
                        'platform': conn,
                        'conversation_id': msg['conversation_id'],
                        'sender_id': msg['sender_id'],
                        'sender_name': msg['sender_name'],
                        'message_text': msg['message_text'],
                        'direction': 'inbound',
                        'timestamp': msg['timestamp'],
                    }
                )
                if created:
                    from .classifier import classify_and_link
                    classify_and_link(dm)
                break
    except Exception:
        pass

    return Response({'status': 'ok'})


# ── Product Catalog ──

class ProductViewSet(viewsets.ModelViewSet):
    serializer_class = ProductSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['name', 'sku', 'category', 'keywords']
    filterset_fields = ['category', 'is_active']
    ordering_fields = ['name', 'price', 'created_at']

    def get_queryset(self):
        return Product.objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

    @action(detail=True, methods=['get'])
    def analytics(self, request, pk=None):
        product = self.get_object()
        days = int(request.query_params.get('days', 30))
        data = get_product_analytics(product, days=days)
        # Convert recent messages to serialized data
        recent = []
        for cls in data.pop('recent_messages', []):
            recent.append({
                'message': DirectMessageSerializer(cls.message).data,
                'category': cls.category,
            })
        data['recent_messages'] = recent
        return Response(data)


@api_view(['POST'])
def upload_catalog(request):
    if 'csv_file' not in request.FILES:
        return Response({'error': 'csv_file is required.'}, status=400)

    csv_file = request.FILES['csv_file']
    if not csv_file.name.endswith('.csv'):
        return Response({'error': 'Only CSV files are accepted.'}, status=400)
    if csv_file.size > 5 * 1024 * 1024:
        return Response({'error': 'File too large (max 5MB).'}, status=400)

    imported, failed, errors = import_catalog_csv(request.user, csv_file)
    return Response({
        'imported': imported,
        'failed': failed,
        'errors': errors[:10],
    })


@api_view(['GET'])
def download_csv_template(request):
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="product_catalog_template.csv"'
    writer = csv.writer(response)
    writer.writerow(['sku', 'name', 'category', 'price', 'keywords'])
    writer.writerow(['SKU001', 'Blue Cotton T-Shirt', 'Clothing', '599', 'tshirt, blue shirt, cotton tee'])
    writer.writerow(['SKU002', 'Wireless Earbuds Pro', 'Electronics', '2499', 'earbuds, earphones, wireless'])
    writer.writerow(['SKU003', 'Organic Face Cream', 'Beauty', '899', 'face cream, moisturizer, skincare'])
    return response


@api_view(['GET'])
def catalog_upload_history(request):
    uploads = CatalogUpload.objects.filter(user=request.user).order_by('-uploaded_at')[:20]
    return Response(CatalogUploadSerializer(uploads, many=True).data)


# ── DM Explorer ──

class DMListView(generics.ListAPIView):
    serializer_class = DirectMessageSerializer

    def get_queryset(self):
        qs = DirectMessage.objects.filter(
            user=self.request.user
        ).select_related('platform', 'classification').prefetch_related(
            'classification__matched_products'
        )

        params = self.request.query_params

        # Direction filter
        direction = params.get('direction')
        if direction in ('inbound', 'outbound'):
            qs = qs.filter(direction=direction)

        # Search
        search = params.get('search')
        if search:
            qs = qs.filter(message_text__icontains=search)

        # Category filter
        category = params.get('category')
        if category:
            qs = qs.filter(classification__category=category)

        # Platform filter
        platform = params.get('platform')
        if platform:
            qs = qs.filter(platform__platform=platform)

        # Product filter
        product_id = params.get('product')
        if product_id:
            qs = qs.filter(classification__matched_products__id=product_id)

        # Resolved filter
        resolved = params.get('resolved')
        if resolved == 'true':
            qs = qs.filter(is_resolved=True)
        elif resolved == 'false':
            qs = qs.filter(is_resolved=False)

        # Date range
        date_from = params.get('date_from')
        if date_from:
            qs = qs.filter(timestamp__date__gte=date_from)
        date_to = params.get('date_to')
        if date_to:
            qs = qs.filter(timestamp__date__lte=date_to)

        return qs


@api_view(['POST'])
def toggle_resolved(request, pk):
    dm = get_object_or_404(DirectMessage, pk=pk, user=request.user)
    dm.is_resolved = not dm.is_resolved
    dm.save(update_fields=['is_resolved'])
    return Response({'id': dm.id, 'is_resolved': dm.is_resolved})


@api_view(['POST'])
def mark_read(request, pk):
    dm = get_object_or_404(DirectMessage, pk=pk, user=request.user)
    dm.is_read = True
    dm.save(update_fields=['is_read'])
    return Response({'id': dm.id, 'is_read': dm.is_read})


@api_view(['POST'])
def bulk_resolve(request):
    ids = request.data.get('ids', [])
    if not ids:
        return Response({'error': 'ids list is required.'}, status=400)
    count = DirectMessage.objects.filter(
        user=request.user, id__in=ids
    ).update(is_resolved=True)
    return Response({'resolved_count': count})


# ── Dashboard & Analytics ──

@api_view(['GET'])
def dashboard(request):
    user = request.user
    days = int(request.query_params.get('days', 30))

    stats = get_dm_stats(user)
    top_products = get_top_products(user, limit=5, days=days)
    category_data = list(get_category_breakdown(user, days=days))
    platform_data = list(get_platform_breakdown(user, days=days))
    daily_data = list(get_daily_volume(user, days=days))

    return Response({
        'stats': stats,
        'top_products': ProductSerializer(top_products, many=True).data,
        'category_breakdown': category_data,
        'daily_volume': [
            {'date': item['date'].isoformat(), 'count': item['count']}
            for item in daily_data
        ],
        'platform_breakdown': [
            {'platform': item['platform__platform'], 'count': item['count']}
            for item in platform_data
        ],
    })


@api_view(['GET'])
def insights(request):
    user = request.user
    days = int(request.query_params.get('days', 30))

    category_data = list(get_category_breakdown(user, days=days))
    peak_hours = list(get_peak_hours(user, days=days))
    top_products = get_top_products(user, limit=10, days=days)
    platform_data = list(get_platform_breakdown(user, days=days))

    # Generate text insights
    text_insights = []
    total_classified = sum(c['count'] for c in category_data)

    for cat in category_data:
        pct = round(cat['count'] / total_classified * 100) if total_classified else 0
        label = dict(MessageClassification.CATEGORY_CHOICES).get(cat['category'], cat['category'])
        text_insights.append({
            'message': f"{pct}% of queries are {label}",
            'type': 'category',
        })

    if peak_hours:
        peak = max(peak_hours, key=lambda x: x['count'])
        text_insights.append({
            'message': f"Peak DM hour: {peak['hour']}:00 - {peak['hour'] + 1}:00",
            'type': 'timing',
        })

    # Product-specific insights
    for product in top_products[:3]:
        if product.mention_count > 0:
            pa = get_product_analytics(product, days=days)
            for cat in pa['category_breakdown']:
                pct = round(cat['count'] / pa['total_mentions'] * 100) if pa['total_mentions'] else 0
                if pct >= 30:
                    label = dict(MessageClassification.CATEGORY_CHOICES).get(cat['category'], cat['category'])
                    text_insights.append({
                        'message': f"{product.name} has {pct}% {label}",
                        'type': 'product',
                    })

    return Response({
        'insights': text_insights,
        'category_breakdown': category_data,
        'peak_hours': peak_hours,
        'top_products': ProductSerializer(top_products, many=True).data,
        'platform_breakdown': [
            {'platform': item['platform__platform'], 'count': item['count']}
            for item in platform_data
        ],
    })


@api_view(['GET'])
def export_report(request):
    from datetime import timedelta
    from django.utils import timezone as tz

    days = int(request.query_params.get('days', 30))
    since = tz.now() - timedelta(days=days)

    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="dm_report_{days}d.csv"'
    writer = csv.writer(response)
    writer.writerow(['Timestamp', 'Platform', 'Sender', 'Message', 'Category', 'Products', 'Resolved'])

    dms = DirectMessage.objects.filter(
        user=request.user, direction='inbound', timestamp__gte=since
    ).select_related('platform', 'classification').prefetch_related(
        'classification__matched_products'
    ).order_by('-timestamp')

    for dm in dms:
        cls = getattr(dm, 'classification', None)
        products = ', '.join(p.name for p in cls.matched_products.all()) if cls else ''
        writer.writerow([
            dm.timestamp.strftime('%Y-%m-%d %H:%M'),
            dm.platform.get_platform_display(),
            dm.sender_name,
            dm.message_text,
            cls.get_category_display() if cls else 'Unclassified',
            products,
            'Yes' if dm.is_resolved else 'No',
        ])

    return response


# ── Sync ──

@api_view(['POST'])
def sync_messages(request):
    platform = request.data.get('platform')

    if platform:
        # Sync specific platform
        connection = get_object_or_404(
            SocialPlatform, user=request.user, platform=platform, is_active=True
        )
        try:
            count = sync_platform_messages(connection)
            return Response({'platform': platform, 'synced': count})
        except Exception as e:
            return Response({'error': str(e)}, status=400)
    else:
        # Sync all platforms
        results = sync_all_platforms(request.user)
        total = sum(r['synced'] for r in results.values())
        errors = {p: r['error'] for p, r in results.items() if r['error']}
        return Response({
            'total_synced': total,
            'per_platform': results,
            'errors': errors,
        })


# ── Onboarding Status ──

@api_view(['GET'])
def onboarding_status(request):
    user = request.user
    platforms = SocialPlatform.objects.filter(user=user, is_active=True)
    has_products = Product.objects.filter(user=user).exists()
    has_messages = DirectMessage.objects.filter(user=user).exists()

    return Response({
        'has_connected_platforms': platforms.exists(),
        'connected_platforms': list(platforms.values_list('platform', flat=True)),
        'has_products': has_products,
        'product_count': Product.objects.filter(user=user).count(),
        'has_messages': has_messages,
        'setup_complete': platforms.exists() and has_products,
    })
