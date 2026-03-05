from django.urls import path, include
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from . import views

router = DefaultRouter()
router.register(r'products', views.ProductViewSet, basename='products')

urlpatterns = [
    # Auth
    path('api/auth/register/', views.RegisterView.as_view(), name='register'),
    path('api/auth/login/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('api/auth/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('api/auth/me/', views.me_view, name='me'),

    # Onboarding
    path('api/onboarding/status/', views.onboarding_status, name='onboarding_status'),

    # Platform connections
    path('api/platforms/', views.PlatformListView.as_view(), name='platform_list'),
    path('api/platforms/available/', views.available_platforms, name='available_platforms'),
    path('api/platforms/<str:platform>/connect/', views.connect_platform_url, name='connect_platform'),
    path('api/platforms/<str:platform>/callback/', views.platform_callback, name='platform_callback'),
    path('api/platforms/whatsapp/setup/', views.setup_whatsapp, name='setup_whatsapp'),
    path('api/platforms/<int:pk>/disconnect/', views.disconnect_platform, name='disconnect_platform'),
    path('api/platforms/<int:pk>/reconnect/', views.reconnect_platform, name='reconnect_platform'),

    # Webhooks
    path('api/webhooks/whatsapp/', views.whatsapp_webhook, name='whatsapp_webhook'),

    # Catalog
    path('api/catalog/upload/', views.upload_catalog, name='upload_catalog'),
    path('api/catalog/template/', views.download_csv_template, name='csv_template'),
    path('api/catalog/history/', views.catalog_upload_history, name='catalog_history'),

    # Products (CRUD via router)
    path('api/', include(router.urls)),

    # DM Explorer
    path('api/messages/', views.DMListView.as_view(), name='dm_list'),
    path('api/messages/<int:pk>/toggle-resolved/', views.toggle_resolved, name='toggle_resolved'),
    path('api/messages/<int:pk>/mark-read/', views.mark_read, name='mark_read'),
    path('api/messages/bulk-resolve/', views.bulk_resolve, name='bulk_resolve'),

    # Dashboard & Analytics
    path('api/dashboard/', views.dashboard, name='dashboard'),
    path('api/insights/', views.insights, name='insights'),
    path('api/export/', views.export_report, name='export_report'),

    # Sync
    path('api/sync/', views.sync_messages, name='sync_messages'),
]
