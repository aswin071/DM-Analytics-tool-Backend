from django.contrib import admin
from .models import SocialPlatform, Product, DirectMessage, MessageClassification, CatalogUpload


@admin.register(SocialPlatform)
class SocialPlatformAdmin(admin.ModelAdmin):
    list_display = ('user', 'platform', 'username', 'is_active', 'connected_at', 'last_synced')
    list_filter = ('platform', 'is_active')
    search_fields = ('username', 'user__username')


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ('name', 'sku', 'category', 'price', 'user', 'is_active')
    list_filter = ('category', 'is_active')
    search_fields = ('name', 'sku', 'keywords')


@admin.register(DirectMessage)
class DirectMessageAdmin(admin.ModelAdmin):
    list_display = ('sender_name', 'platform', 'direction', 'timestamp', 'is_resolved', 'short_text')
    list_filter = ('platform__platform', 'direction', 'is_resolved')
    search_fields = ('message_text', 'sender_name')
    date_hierarchy = 'timestamp'

    def short_text(self, obj):
        return obj.message_text[:80]
    short_text.short_description = 'Message'


@admin.register(MessageClassification)
class MessageClassificationAdmin(admin.ModelAdmin):
    list_display = ('message', 'category', 'classified_at')
    list_filter = ('category',)


@admin.register(CatalogUpload)
class CatalogUploadAdmin(admin.ModelAdmin):
    list_display = ('user', 'rows_imported', 'rows_failed', 'uploaded_at')
