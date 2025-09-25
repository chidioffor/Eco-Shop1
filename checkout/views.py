from django.shortcuts import (
    render, HttpResponse, redirect, reverse, get_object_or_404
)
from django.conf import settings
from django.contrib import messages
from django.views.decorators.http import require_POST

from products.models import Product
from .forms import OrderForm
from basket.contexts import basket_contents
from .models import Order, OrderLineItem
from profiles.models import AccountProfile
from profiles.forms import AccountProfileForm

import stripe
import json

# Create your views here.


@require_POST
def store_checkout_info(request):
    """
    Store checkout information in Stripe PaymentIntent metadata.

    Extracts the PaymentIntent ID from the client secret and updates
    its metadata to include:
    - Current basket contents
    - Whether the user wants to save their info
    - The username (if authenticated)

    If the update fails, returns an error response.
    """
    def _extract_payment_intent_id(client_secret):
        return client_secret.split('_secret')[0]

    def _update_payment_intent_metadata(payment_intent_id, request):
        metadata = {
            'basket': json.dumps(request.session.get('basket', {})),
            'save_info': request.POST.get('save_info'),
            'username': request.user,
        }
        stripe.PaymentIntent.modify(payment_intent_id, metadata=metadata)

    def _handle_error(request, error_message):
        messages.error(request, 'Unsuccessful payment processing. \
                       Try again later.')
        return HttpResponse(content=error_message, status=400)

    client_secret = request.POST.get('client_secret')
    if not client_secret:
        return _handle_error(request, 'Client secret is missing.')

    payment_intent_id = _extract_payment_intent_id(client_secret)

    stripe.api_key = settings.STRIPE_SECRET_KEY

    try:
        _update_payment_intent_metadata(payment_intent_id, request)
        return HttpResponse(status=200)
    except Exception as e:
        return _handle_error(request, str(e))


def checkout(request):
    """
    GET:
      - Validate basket is not empty.
      - Calculate totals and create a Stripe PaymentIntent.
      - Initialize the OrderForm (prefill if user has a profile).
      - Render the checkout page with context.

    POST:
      - Validate and process submitted order form.
      - Create Order and OrderLineItems.
      - Redirect to checkout completion page on success.
    """
    stripe_public_key = settings.STRIPE_PUBLIC_KEY
    stripe_secret_key = settings.STRIPE_SECRET_KEY

    def handle_post_request(request, stripe_secret_key):
        basket = request.session.get('basket', {})
        order_form = OrderForm(get_form_data(request))

        if order_form.is_valid():
            order = create_order(order_form, basket, request)
            if not order:
                return redirect(reverse('view_basket'))

            if not process_order_line_items(basket, order):
                return redirect(reverse('view_basket'))

            request.session['save_info'] = 'save-info' in request.POST
            messages.success(
                request,
                'Payment authorised! We are preparing your eco-friendly order.',
            )
            return redirect(reverse(
                'checkout_complete', args=[order.order_number])
                )

        messages.error(request, 'Form error. Please recheck your details.')
        return redirect(reverse('view_basket'))

    def create_order(order_form, basket, request):
        order = order_form.save(commit=False)

        client_secret = request.POST.get('client_secret')
        if not client_secret:
            messages.error(
                request, "Missing payment information. Please try again."
                )
            return None

        payment_intent_id = client_secret.split('_secret')[0]
        order.stripe_payment_intent_id = payment_intent_id
        order.existing_basket = json.dumps(basket)
        order.delivery_eta = order.estimate_delivery_eta()
        order.payment_status = Order.PaymentStatus.PAID
        order.payment_message = 'Stripe confirmed your payment.'
        order.order_status = Order.OrderStatus.PROCESSING

        try:
            order.save()

        except Exception as e:
            messages.error(request, f"Order saving failed: {str(e)}")
            return None

        return order

    def process_order_line_items(basket, order):
        try:
            for item_id, item_data in basket.items():
                product = Product.objects.get(id=item_id)
                if not product.can_fulfil_order(item_data):
                    message = (
                        f'Only {product.inventory_count} of {product.name} remain. '
                        'Please adjust your basket before checking out again.'
                    )
                    messages.error(request, message)
                    order.mark_payment_failed(message)
                    order.delete()
                    return False
                OrderLineItem.objects.create(
                    order=order, product=product, quantity=item_data
                    )
        except Product.DoesNotExist:
            message = (
                "One of the products in your basket wasn't found in our database. "
                "Please call us for assistance!"
            )
            messages.error(request, message)
            order.mark_payment_failed(message)
            order.delete()
            return False
        return True

    def calculate_total(basket):
        return sum(
            item_data * Product.objects.get(id=item_id).price for item_id, item_data in basket.items()  # noqa
            )

    def estimate_delivery_from_basket(basket_items):
        estimates = [
            item['product'].estimate_delivery_date()
            for item in basket_items
            if hasattr(item.get('product'), 'estimate_delivery_date')
        ]
        if not estimates:
            return None
        return max(estimates)

    def handle_get_request(request, stripe_public_key):
        basket = request.session.get('basket', {})
        if not basket:
            messages.error(request, "Your basket is currently empty")
            return redirect(reverse('products'))

        current_basket = basket_contents(request)
        total = current_basket['grand_total']
        stripe_total = round(total * 100)
        stripe.api_key = settings.STRIPE_SECRET_KEY

        payment_intent = create_payment_intent(stripe_total)
        if not payment_intent:
            return redirect(reverse('view_basket'))

        order_form = initialize_order_form(request)
        estimated_delivery_date = estimate_delivery_from_basket(
            current_basket['basket_items']
        )

        context = {
            'order_form': order_form,
            'stripe_public_key': stripe_public_key,
            'client_secret': payment_intent.client_secret,
            'estimated_delivery_date': estimated_delivery_date,
        }

        return render(request, 'checkout/checkout.html', context)

    def create_payment_intent(stripe_total):
        try:
            return stripe.PaymentIntent.create(
                amount=stripe_total,
                currency=settings.STRIPE_CURRENCY
            )
        except stripe.error.StripeError as e:
            messages.error(
                request, f"An error occurred while processing your payment: {str(e)}"  # noqa
                )
            return None

    def initialize_order_form(request):
        if request.user.is_authenticated:
            try:
                profile = AccountProfile.objects.get(user=request.user)
                return OrderForm(initial={
                    'customer_name': profile.user.get_username(),
                    'email': profile.user.email,
                    'phone_number': profile.primary_phone_number,
                    'address': profile.primary_address,
                    'city': profile.primary_city,
                    'county': profile.primary_county,
                    'postcode': profile.primary_postcode,
                    'country': profile.primary_country,
                })
            except AccountProfile.DoesNotExist:
                pass

        return OrderForm()

    def get_form_data(request):
        return {
            'customer_name': request.POST['customer_name'],
            'email': request.POST['email'],
            'phone_number': request.POST['phone_number'],
            'address': request.POST['address'],
            'city': request.POST['city'],
            'county': request.POST['county'],
            'postcode': request.POST['postcode'],
            'country': request.POST['country'],
            'delivery_notes': request.POST.get('delivery_notes', ''),
        }

    if request.method == 'POST':
        return handle_post_request(request, stripe_secret_key)

    return handle_get_request(request, stripe_public_key)


def checkout_complete(request, order_number):
    """
    Handle successful checkouts and render the success page.
    - If the user is authenticated, attach the user's profile to the order
      and optionally update their saved profile information.
    - Display a success message with the order number.
    - Clear the basket from the session.
    - Render the checkout success template with order details.

    Args:
        request: The HTTP request object.
        order_number: The unique identifier for the order.
    """
    def update_order_profile(order, user, save_info):

        profile = AccountProfile.objects.get(user=user)
        order.account_profile = profile
        order.save()

        if save_info:
            update_profile_data(profile, order)

    def update_profile_data(profile, order):

        profile_data = {
            'primary_phone_number': order.phone_number,
            'primary_address': order.address,
            'primary_city': order.city,
            'primary_county': order.county,
            'primary_postcode': order.postcode,
            'primary_country': order.country,
        }
        account_profile_form = AccountProfileForm(
            profile_data, instance=profile
            )
        if account_profile_form.is_valid():
            account_profile_form.save()

    def send_success_message(request, order_number, email):

        messages.success(request, (
            f'Order completed! Your order number is {order_number}. '
            f'Confirmation email has been sent to {email}.'
        ))

    def clear_basket(request):

        request.session.pop('basket', None)

    def render_checkout_complete_page(request, order):

        return render(
            request, 'checkout/checkout_complete.html', {'order': order}
            )

    save_info = request.session.get('save_info')
    order = get_object_or_404(Order, order_number=order_number)

    if request.user.is_authenticated:
        update_order_profile(order, request.user, save_info)

    send_success_message(request, order_number, order.email)
    clear_basket(request)

    return render_checkout_complete_page(request, order)
