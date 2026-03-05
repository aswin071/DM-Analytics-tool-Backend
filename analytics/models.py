from django.db import models
from django.conf import settings
from django.utils import timezone


class SocialPlatform(models.Model):
    """Connected social media account for a user."""
    PLATFORM_CHOICES = [
        ('instagram', 'Instagram'),
        ('facebook', 'Facebook'),
        ('twitter', 'Twitter / X'),
        ('whatsapp', 'WhatsApp Business'),
    ]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='platforms')
    platform = models.CharField(max_length=20, choices=PLATFORM_CHOICES)
    platform_user_id = models.CharField(max_length=255)
    page_id = models.CharField(max_length=255, blank=True, help_text='Page/Business ID for Meta platforms')
    username = models.CharField(max_length=255, blank=True)
    access_token = models.TextField()
    token_expires_at = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    connected_at = models.DateTimeField(auto_now_add=True)
    last_synced = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = ('user', 'platform', 'platform_user_id')

    def __str__(self):
        return f"{self.get_platform_display()} — {self.username or self.platform_user_id}"

    @property
    def is_token_expired(self):
        if not self.token_expires_at:
            return False
        return timezone.now() >= self.token_expires_at


class Product(models.Model):
    """Product from the uploaded catalog."""
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='products')
    sku = models.CharField(max_length=100)
    name = models.CharField(max_length=255)
    category = models.CharField(max_length=100, blank=True)
    price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    keywords = models.TextField(blank=True, help_text='Comma-separated keywords/aliases for regex matching')
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('user', 'sku')

    def __str__(self):
        return f"{self.name} ({self.sku})"

    def get_keywords_list(self):
        """Return list of keywords for regex matching, including the product name."""
        kw = [self.name.lower()]
        if self.keywords:
            kw.extend(k.strip().lower() for k in self.keywords.split(',') if k.strip())
        return kw


class DirectMessage(models.Model):
    """A single DM from any connected platform."""
    DIRECTION_CHOICES = [
        ('inbound', 'Inbound'),
        ('outbound', 'Outbound'),
    ]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='messages')
    platform = models.ForeignKey(SocialPlatform, on_delete=models.CASCADE, related_name='messages')
    platform_message_id = models.CharField(max_length=255, unique=True)
    conversation_id = models.CharField(max_length=255, blank=True, db_index=True)
    sender_id = models.CharField(max_length=255)
    sender_name = models.CharField(max_length=255, blank=True)
    message_text = models.TextField(blank=True)
    direction = models.CharField(max_length=10, choices=DIRECTION_CHOICES, default='inbound')
    timestamp = models.DateTimeField(db_index=True)
    is_read = models.BooleanField(default=False)
    is_resolved = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-timestamp']

    def __str__(self):
        return f"[{self.platform.platform}] {self.sender_name}: {self.message_text[:50]}"


class MessageClassification(models.Model):
    """Classification result for a DM — links message to category and product."""
    CATEGORY_CHOICES = [
        ('pricing', 'Pricing Query'),
        ('stock', 'Stock / Availability'),
        ('complaint', 'Complaint'),
        ('compliment', 'Compliment'),
        ('purchase_intent', 'Purchase Intent'),
        ('general', 'General Inquiry'),
    ]

    message = models.OneToOneField(DirectMessage, on_delete=models.CASCADE, related_name='classification')
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES, default='general', db_index=True)
    matched_products = models.ManyToManyField(Product, blank=True, related_name='classifications')
    confidence_keywords = models.TextField(blank=True, help_text='Keywords that triggered this classification')
    classified_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.get_category_display()} — {self.message}"


class CatalogUpload(models.Model):
    """Track CSV catalog uploads."""
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='catalog_uploads')
    file = models.FileField(upload_to='catalogs/')
    rows_imported = models.IntegerField(default=0)
    rows_failed = models.IntegerField(default=0)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Upload by {self.user.username} — {self.rows_imported} products ({self.uploaded_at:%Y-%m-%d})"
