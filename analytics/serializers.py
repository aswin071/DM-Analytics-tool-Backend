from rest_framework import serializers
from django.contrib.auth.models import User
from .models import SocialPlatform, Product, DirectMessage, MessageClassification, CatalogUpload


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=8)
    password_confirm = serializers.CharField(write_only=True)

    class Meta:
        model = User
        fields = ('id', 'username', 'email', 'password', 'password_confirm')

    def validate(self, data):
        if data['password'] != data['password_confirm']:
            raise serializers.ValidationError({'password_confirm': 'Passwords do not match.'})
        return data

    def create(self, validated_data):
        validated_data.pop('password_confirm')
        return User.objects.create_user(**validated_data)


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ('id', 'username', 'email', 'date_joined')
        read_only_fields = fields


class SocialPlatformSerializer(serializers.ModelSerializer):
    platform_display = serializers.CharField(source='get_platform_display', read_only=True)
    is_token_expired = serializers.BooleanField(read_only=True)

    class Meta:
        model = SocialPlatform
        fields = (
            'id', 'platform', 'platform_display', 'platform_user_id',
            'username', 'is_active', 'is_token_expired',
            'connected_at', 'last_synced',
        )
        read_only_fields = fields


class WhatsAppSetupSerializer(serializers.Serializer):
    phone_number_id = serializers.CharField(max_length=255)
    access_token = serializers.CharField()


class ProductSerializer(serializers.ModelSerializer):
    mention_count = serializers.IntegerField(read_only=True, default=0)

    class Meta:
        model = Product
        fields = (
            'id', 'sku', 'name', 'category', 'price',
            'keywords', 'is_active', 'created_at', 'updated_at', 'mention_count',
        )
        read_only_fields = ('id', 'created_at', 'updated_at', 'mention_count')

    def validate_sku(self, value):
        user = self.context['request'].user
        qs = Product.objects.filter(user=user, sku=value)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError('A product with this SKU already exists.')
        return value


class MessageClassificationSerializer(serializers.ModelSerializer):
    category_display = serializers.CharField(source='get_category_display', read_only=True)
    matched_products = ProductSerializer(many=True, read_only=True)

    class Meta:
        model = MessageClassification
        fields = ('category', 'category_display', 'matched_products', 'confidence_keywords', 'classified_at')


class DirectMessageSerializer(serializers.ModelSerializer):
    platform_name = serializers.CharField(source='platform.get_platform_display', read_only=True)
    platform_type = serializers.CharField(source='platform.platform', read_only=True)
    classification = MessageClassificationSerializer(read_only=True)

    class Meta:
        model = DirectMessage
        fields = (
            'id', 'platform_name', 'platform_type', 'platform_message_id',
            'conversation_id', 'sender_id', 'sender_name', 'message_text',
            'direction', 'timestamp', 'is_read', 'is_resolved', 'classification',
        )
        read_only_fields = (
            'id', 'platform_name', 'platform_type', 'platform_message_id',
            'conversation_id', 'sender_id', 'sender_name', 'message_text',
            'direction', 'timestamp', 'classification',
        )


class CatalogUploadSerializer(serializers.ModelSerializer):
    class Meta:
        model = CatalogUpload
        fields = ('id', 'file', 'rows_imported', 'rows_failed', 'uploaded_at')
        read_only_fields = ('id', 'rows_imported', 'rows_failed', 'uploaded_at')


# ── Analytics Response Serializers ──

class DashboardStatsSerializer(serializers.Serializer):
    total = serializers.IntegerField()
    today = serializers.IntegerField()
    this_week = serializers.IntegerField()
    this_month = serializers.IntegerField()
    unanswered = serializers.IntegerField()


class CategoryBreakdownSerializer(serializers.Serializer):
    category = serializers.CharField()
    count = serializers.IntegerField()


class DailyVolumeSerializer(serializers.Serializer):
    date = serializers.DateField()
    count = serializers.IntegerField()


class PlatformBreakdownSerializer(serializers.Serializer):
    platform = serializers.CharField(source='platform__platform')
    count = serializers.IntegerField()


class PeakHourSerializer(serializers.Serializer):
    hour = serializers.IntegerField()
    count = serializers.IntegerField()


class ProductAnalyticsSerializer(serializers.Serializer):
    total_mentions = serializers.IntegerField()
    purchase_intent_score = serializers.FloatField()
    category_breakdown = CategoryBreakdownSerializer(many=True)


class InsightSerializer(serializers.Serializer):
    message = serializers.CharField()
    type = serializers.CharField()
