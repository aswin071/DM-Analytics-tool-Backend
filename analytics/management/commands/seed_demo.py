"""Seed demo data for testing the dashboard."""
import random
from datetime import timedelta
from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from django.utils import timezone
from analytics.models import SocialPlatform, Product, DirectMessage
from analytics.classifier import classify_and_link


DEMO_PRODUCTS = [
    ('SKU001', 'Blue Cotton T-Shirt', 'Clothing', 599, 'tshirt, blue shirt, cotton tee'),
    ('SKU002', 'Wireless Earbuds Pro', 'Electronics', 2499, 'earbuds, earphones, wireless'),
    ('SKU003', 'Organic Face Cream', 'Beauty', 899, 'face cream, moisturizer, skincare'),
    ('SKU004', 'Running Shoes X1', 'Footwear', 3499, 'shoes, running, sneakers'),
    ('SKU005', 'Leather Wallet Classic', 'Accessories', 1299, 'wallet, leather wallet, purse'),
]

DEMO_MESSAGES = [
    # Pricing queries
    "Hi, what's the price of the blue cotton t-shirt?",
    "How much do the wireless earbuds cost?",
    "Can you tell me the rate for running shoes?",
    "Any discount on the leather wallet?",
    "What's the MRP of face cream?",
    "Kya price hai earbuds ka?",
    "Budget earphones available?",
    # Stock queries
    "Is the blue shirt available in size L?",
    "Do you have earbuds in stock?",
    "When will running shoes be back in stock?",
    "Can you deliver the face cream by tomorrow?",
    "Is the wallet available in brown?",
    "Earbuds milega kya?",
    # Complaints
    "The t-shirt I received is defective",
    "Earbuds stopped working after 2 days",
    "I got the wrong shoes, very disappointed",
    "Face cream caused skin issues, want a refund",
    "Terrible quality wallet, leather is peeling",
    "Not happy with the product at all",
    # Compliments
    "Love the blue shirt, amazing quality!",
    "Best earbuds I've ever used, fantastic!",
    "The face cream is wonderful, thank you!",
    "Running shoes are perfect, great product",
    "Beautiful wallet, excellent craftsmanship",
    # Purchase intent
    "I want to buy the blue t-shirt, how to order?",
    "Want to purchase earbuds, do you accept UPI?",
    "I'll take 2 face creams, what's the payment process?",
    "Interested in the running shoes, COD available?",
    "Add wallet to cart, want to checkout",
    "Lena hai earbuds, kaise order karu?",
    # General
    "Do you have any new arrivals?",
    "What's your return policy?",
    "Do you ship internationally?",
    "What materials do you use?",
    "Can I visit your store?",
]

PLATFORMS = ['instagram', 'facebook', 'twitter', 'whatsapp']
SENDER_NAMES = [
    'Priya Sharma', 'Rahul Kumar', 'Sneha Patel', 'Amit Singh', 'Neha Gupta',
    'Vikram Joshi', 'Ananya Reddy', 'Karan Mehta', 'Divya Nair', 'Rohit Verma',
    'Sarah Johnson', 'Mike Chen', 'Emily Davis', 'Alex Thompson', 'Maria Garcia',
]


class Command(BaseCommand):
    help = 'Seed demo data: products, platform connections, and sample DMs'

    def add_arguments(self, parser):
        parser.add_argument('--messages', type=int, default=200, help='Number of demo messages')

    def handle(self, *args, **options):
        num_messages = options['messages']

        # Create or get demo user
        user, created = User.objects.get_or_create(
            username='demo',
            defaults={'email': 'demo@example.com'}
        )
        if created:
            user.set_password('demo1234')
            user.save()
            self.stdout.write(f'Created demo user (username: demo, password: demo1234)')

        # Create demo platform connections
        for platform in PLATFORMS:
            SocialPlatform.objects.get_or_create(
                user=user,
                platform=platform,
                platform_user_id=f'demo_{platform}_123',
                defaults={
                    'username': f'demo_store_{platform}',
                    'access_token': 'demo_token_not_real',
                    'is_active': True,
                }
            )
        self.stdout.write(f'Created {len(PLATFORMS)} platform connections')

        # Create products
        for sku, name, category, price, keywords in DEMO_PRODUCTS:
            Product.objects.update_or_create(
                user=user, sku=sku,
                defaults={'name': name, 'category': category, 'price': price, 'keywords': keywords}
            )
        self.stdout.write(f'Created {len(DEMO_PRODUCTS)} products')

        # Create DMs spread over last 30 days
        connections = list(SocialPlatform.objects.filter(user=user, is_active=True))
        now = timezone.now()
        created_count = 0

        for i in range(num_messages):
            conn = random.choice(connections)
            msg_text = random.choice(DEMO_MESSAGES)
            sender = random.choice(SENDER_NAMES)
            hours_ago = random.randint(0, 30 * 24)  # Last 30 days
            ts = now - timedelta(hours=hours_ago)

            dm, created = DirectMessage.objects.get_or_create(
                platform_message_id=f'demo_{conn.platform}_{i}',
                defaults={
                    'user': user,
                    'platform': conn,
                    'conversation_id': f'convo_{sender.replace(" ", "_").lower()}_{conn.platform}',
                    'sender_id': f'sender_{sender.replace(" ", "_").lower()}',
                    'sender_name': sender,
                    'message_text': msg_text,
                    'direction': 'inbound',
                    'timestamp': ts,
                    'is_resolved': random.random() < 0.6,
                }
            )
            if created:
                classify_and_link(dm)
                created_count += 1

        self.stdout.write(self.style.SUCCESS(
            f'Seeded {created_count} demo messages across {len(PLATFORMS)} platforms.'
        ))
