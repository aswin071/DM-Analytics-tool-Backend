"""
Regex & keyword-based DM classifier.
No AI/ML — pure pattern matching.
"""
import re
from .models import Product, MessageClassification

# Keyword patterns for each category (order matters — first match wins)
CATEGORY_PATTERNS = {
    'pricing': [
        r'\bprice\b', r'\bcost\b', r'\bhow much\b', r'\brate\b', r'\bcharges?\b',
        r'\bdiscount\b', r'\boffer\b', r'\bdeal\b', r'\bcheap\b', r'\bexpensive\b',
        r'\bbudget\b', r'\bafford\b', r'\bMRP\b', r'\bquote\b', r'\bestimate\b',
        r'\bkitna\b', r'\bkya rate\b', r'\bkya price\b', r'\bkitne (ka|ki|ke)\b',
    ],
    'stock': [
        r'\bavailable\b', r'\bstock\b', r'\bin stock\b', r'\bout of stock\b',
        r'\bdelivery\b', r'\bship(ping)?\b', r'\bwhen.*(get|arrive|deliver)\b',
        r'\brestock\b', r'\bback in stock\b', r'\bhave this\b',
        r'\bmilega\b', r'\bmil (jayega|sakta)\b', r'\bavailability\b',
    ],
    'complaint': [
        r'\bcomplaint\b', r'\bdefective\b', r'\bbroken\b', r'\bdamage[d]?\b',
        r'\bwrong\b', r'\bbad quality\b', r'\bterrible\b', r'\bawful\b',
        r'\bworst\b', r'\bdisappoint\b', r'\brefund\b', r'\breturn\b',
        r'\bnot (working|happy|satisfied)\b', r'\bissue\b', r'\bproblem\b',
        r'\bfraud\b', r'\bscam\b', r'\bcheat\b',
    ],
    'compliment': [
        r'\blove (it|this|your)\b', r'\bamazing\b', r'\bgreat\b', r'\bawesome\b',
        r'\bbeautiful\b', r'\bperfect\b', r'\bexcellent\b', r'\bbest\b',
        r'\bfantastic\b', r'\bwonderful\b', r'\bhappy\b', r'\bsatisfied\b',
        r'\bthank(s| you)\b', r'\bsuperb\b', r'\bnice\b',
    ],
    'purchase_intent': [
        r'\bbuy\b', r'\border\b', r'\bpurchase\b', r'\bbook\b',
        r'\bwant (to|this)\b', r'\binterested\b', r'\bi\'?ll take\b',
        r'\badd to cart\b', r'\bcheckout\b', r'\bpay(ment)?\b',
        r'\bCOD\b', r'\bcash on delivery\b', r'\bUPI\b',
        r'\blena (hai|h|he)\b', r'\bkharidna\b', r'\bmangwa\b',
    ],
}


def classify_message(message_text):
    """
    Classify message text into a category based on keyword matching.
    Returns (category, matched_keywords).
    """
    text = message_text.lower().strip()
    if not text:
        return 'general', []

    for category, patterns in CATEGORY_PATTERNS.items():
        matched = []
        for pattern in patterns:
            if re.search(pattern, text, re.IGNORECASE):
                matched.append(pattern)
        if matched:
            return category, matched

    return 'general', []


def match_products(message_text, user):
    """
    Match message text against user's product catalog.
    Returns list of matched Product instances.
    """
    text = message_text.lower().strip()
    if not text:
        return []

    products = Product.objects.filter(user=user, is_active=True)
    matched = []

    for product in products:
        for keyword in product.get_keywords_list():
            # Use word boundary matching for keywords
            pattern = r'\b' + re.escape(keyword) + r'\b'
            if re.search(pattern, text, re.IGNORECASE):
                matched.append(product)
                break  # One match per product is enough

    return matched


def classify_and_link(dm_instance):
    """
    Full pipeline: classify a DirectMessage and link to products.
    Creates/updates the MessageClassification record.
    """
    category, keywords = classify_message(dm_instance.message_text)
    matched_products = match_products(dm_instance.message_text, dm_instance.user)

    classification, _ = MessageClassification.objects.update_or_create(
        message=dm_instance,
        defaults={
            'category': category,
            'confidence_keywords': ', '.join(keywords),
        }
    )
    classification.matched_products.set(matched_products)
    return classification
