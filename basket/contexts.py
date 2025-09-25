from django.shortcuts import get_object_or_404
from decimal import Decimal

from django.conf import settings
from django.shortcuts import get_object_or_404

from products.models import Product


def calculate_delivery(total):
    """
    Delivery cost calculation, including amount to qualify for free delivery.

    Args:
        total (Decimal): The existing total value of the basket.

    Returns:
        tuple: A tuple that contains:
            - delivery (Decimal): The delivery cost.
            - free_delivery_delta (Decimal): Remaining amount
              to reach the free delivery threshold.
    """
    if total < settings.FREE_DELIVERY_THRESHOLD:
        delivery = total * Decimal(settings.STANDARD_DELIVERY_PERCENTAGE / 100)
        free_delivery_delta = settings.FREE_DELIVERY_THRESHOLD - total
    else:
        delivery = 0
        free_delivery_delta = 0
    return delivery, free_delivery_delta


def get_basket_items(basket):
    """
    Extract product details and calculate total price and item count
    for all items in the basket.

    Args:
        basket (dict): Dictionary of item IDs and quantities
        stored in the session.

    Returns:
        tuple: A tuple containing:
            - items (list): List of dictionaries with product details.
            - total (Decimal): Total cost of the basket.
            - product_count (int): Total number of items.
    """
    items = []
    total = 0
    product_count = 0

    for item_id, quantity in basket.items():
        product = get_object_or_404(Product, pk=item_id)
        total += quantity * product.price
        product_count += quantity
        items.append({
            'item_id': item_id,
            'quantity': quantity,
            'product': product,
        })

    return items, total, product_count


def basket_contents(request):
    """
    Create basket context containing product details, totals,
    delivery cost, and free delivery threshold information.

    Args:
        request (HttpRequest): HTTP request object.

    Returns:
        dict: Context dictionary with basket items, totals, delivery
        costs, free delivery delta, and the grand total.
    """
    basket = request.session.get('basket', {})
    basket_items, total, product_count = get_basket_items(basket)
    delivery, free_delivery_delta = calculate_delivery(total)
    grand_total = delivery + total

    context = {
        'basket_items': basket_items,
        'total': total,
        'product_count': product_count,
        'delivery': delivery,
        'free_delivery_delta': free_delivery_delta,
        'free_delivery_threshold': settings.FREE_DELIVERY_THRESHOLD,
        'grand_total': grand_total,
    }

    return context
