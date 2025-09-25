import uuid
from datetime import timedelta

from django.db import models

from django.db.models import Sum
from django.conf import settings
from django.core.validators import MinValueValidator
from django_countries.fields import CountryField
from phonenumber_field.modelfields import PhoneNumberField
from django.utils import timezone

from products.models import Product
from profiles.models import AccountProfile

# Create your models here.


class Order(models.Model):
    class OrderStatus(models.TextChoices):
        PENDING = 'pending', 'Pending'
        PROCESSING = 'processing', 'Processing'
        COMPLETED = 'completed', 'Completed'
        CANCELLED = 'cancelled', 'Cancelled'

    class PaymentStatus(models.TextChoices):
        AWAITING = 'awaiting', 'Awaiting Payment'
        PAID = 'paid', 'Paid'
        FAILED = 'failed', 'Failed'

    order_number = models.CharField(max_length=50, unique=True, editable=False)
    account_profile = models.ForeignKey(
        AccountProfile, on_delete=models.SET_NULL,
        blank=True, null=True, related_name='orders'
        )
    customer_name = models.CharField(max_length=255)
    email = models.EmailField(blank=False, null=False)
    address = models.CharField(max_length=255, blank=False, null=False)
    phone_number = PhoneNumberField(
        null=True, blank=True, help_text="Enter phone number with country code"
        )
    city = models.CharField(max_length=100, null=False, blank=False)
    county = models.CharField(max_length=100, null=False, blank=False)
    postcode = models.CharField(max_length=20, blank=True, null=True)
    country = CountryField(
        blank_label='Select Country *', blank=False, null=False
        )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    delivery_cost = models.DecimalField(
        max_digits=6, decimal_places=2, null=False, default=0
        )
    order_total = models.DecimalField(
        max_digits=10, decimal_places=2, null=False, default=0
        )
    grand_total = models.DecimalField(
        max_digits=10, decimal_places=2, null=False, default=0
        )
    existing_basket = models.TextField(null=False, blank=False, default='')
    stripe_payment_intent_id = models.CharField(
        max_length=255, null=False, default=''
        )
    order_status = models.CharField(
        max_length=20,
        choices=OrderStatus.choices,
        default=OrderStatus.PENDING,
    )
    payment_status = models.CharField(
        max_length=20,
        choices=PaymentStatus.choices,
        default=PaymentStatus.AWAITING,
    )
    payment_message = models.CharField(
        max_length=255,
        blank=True,
        help_text="Human friendly status message shown on confirmation page.",
    )
    delivery_eta = models.DateField(
        null=True,
        blank=True,
        help_text="Estimated delivery date presented to customers.",
    )
    delivery_notes = models.TextField(
        blank=True,
        help_text="Optional delivery instructions provided by the customer.",
    )

    def _generate_order_number(self):
        return uuid.uuid4().hex.upper()

    def update_total(self):
        """
        Update order totals including delivery and grand total, then save.
        """
        self.order_total = self.calculate_order_total()
        self.delivery_cost = self.calculate_delivery_cost()
        self.grand_total = self.order_total + self.delivery_cost
        self.save()

    def calculate_order_total(self):
        """
        Calculate the total cost of all related line items.
        """
        return self.lineitems.aggregate(Sum('lineitem_total'))['lineitem_total__sum'] or 0  # noqa

    def calculate_delivery_cost(self):
        """
        Calculate the delivery cost based on order total
        and free delivery threshold
        """
        if self.order_total < settings.FREE_DELIVERY_THRESHOLD:
            return self.order_total * settings.STANDARD_DELIVERY_PERCENTAGE / 100  # noqa
        return 0

    def save(self, *args, **kwargs):
        """
        Override save method to generate order number if missing.
        """
        if not self.order_number:
            self.order_number = self._generate_order_number()
        super().save(*args, **kwargs)

    def __str__(self):
        return self.order_number

    def mark_payment_successful(self, message="Payment confirmed via Stripe"):
        self.payment_status = Order.PaymentStatus.PAID
        self.payment_message = message
        if self.order_status == Order.OrderStatus.PENDING:
            self.order_status = Order.OrderStatus.PROCESSING
        if not self.delivery_eta:
            self.delivery_eta = self.estimate_delivery_eta()
        self.save(update_fields=[
            'payment_status', 'payment_message', 'order_status', 'delivery_eta'
        ])

    def mark_payment_failed(self, message):
        self.payment_status = Order.PaymentStatus.FAILED
        self.payment_message = message[:250]
        self.order_status = Order.OrderStatus.PENDING
        self.save(update_fields=['payment_status', 'payment_message', 'order_status'])

    def estimate_delivery_eta(self):
        days = getattr(settings, 'DEFAULT_DELIVERY_DAYS', 4)
        return timezone.now().date() + timedelta(days=days)

    class Meta:
        verbose_name = 'Order'
        verbose_name_plural = 'Orders'


class OrderLineItem(models.Model):
    """
    Individual line item within an order.
    Links a product to an order icluding quantity and total cost.
    """
    order = models.ForeignKey(
        Order, on_delete=models.CASCADE, related_name='lineitems'
        )
    product = models.ForeignKey(
        Product, null=False, blank=False, on_delete=models.CASCADE
        )
    quantity = models.PositiveIntegerField(
        null=False, blank=False, default=1, validators=[MinValueValidator(1)],
    )
    unit_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        editable=False,
    )
    lineitem_total = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        editable=False,
    )

    def save(self, *args, **kwargs):
        """
        Override save to calculate line item total before saving,
        then update the parent order total.
        """
        self.unit_price = self.product.price
        self.lineitem_total = self.calculate_lineitem_total()
        super().save(*args, **kwargs)
        self.update_order_total()
        self._decrement_inventory()

    def calculate_lineitem_total(self):
        """
        Calculate total price for this line item.
        """
        return self.unit_price * self.quantity

    def update_order_total(self):
        """
        Update the total cost for the related order.
        """
        self.order.update_total()

    def _decrement_inventory(self):
        if self._state.adding:
            self.product.adjust_inventory(-self.quantity)

    def delete(self, *args, **kwargs):
        if not self.product.is_digital:
            self.product.adjust_inventory(self.quantity)
        super().delete(*args, **kwargs)

    def __str__(self):
        return f'SKU {self.product.sku} on order {self.order.order_number}'

    class Meta:
        verbose_name = 'Order Line Item'
        verbose_name_plural = 'Order Line Items'
