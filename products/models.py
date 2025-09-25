from datetime import timedelta

from django.db import models
from django.db.models import F
from django.utils import timezone
from django.utils.text import slugify

# Create your models here.


class Category(models.Model):
    """Metadata used to organise products into navigable groups."""

    name = models.CharField(max_length=200)
    friendly_name = models.CharField(max_length=200, null=True, blank=True)
    slug = models.SlugField(
        max_length=210,
        unique=True,
        blank=True,
        help_text="Used in URLs. Automatically generated from the name if left blank.",
    )
    description = models.TextField(
        blank=True,
        help_text="Optional description shown on category landing pages.",
    )
    icon = models.CharField(
        max_length=80,
        blank=True,
        help_text="Font Awesome icon class to visually represent the category.",
    )
    display_order = models.PositiveIntegerField(
        default=0,
        help_text="Lower numbers appear first in navigation menus.",
    )

    class Meta:
        verbose_name = "Category"
        verbose_name_plural = "Categories"
        ordering = ['display_order', 'name']

    def __str__(self):
        return self.name

    def get_friendly_name(self):
        return self.friendly_name or self.name

    def save(self, *args, **kwargs):
        """Ensure a slug is always available for navigation links."""
        if not self.slug:
            base_slug = slugify(self.friendly_name or self.name)
        else:
            base_slug = self.slug

        slug = base_slug
        counter = 1
        while Category.objects.filter(slug=slug).exclude(pk=self.pk).exists():
            counter += 1
            slug = f"{base_slug}-{counter}"

        self.slug = slug
        super().save(*args, **kwargs)


class Product(models.Model):
    """
    Each product belongs to an optional category, has a unique name and SKU,
    a detailed description, price, optional rating, timestamps for creation
    and updates, and product image.

    Products are ordered by creation date, newest first.
    """
    category = models.ForeignKey(
        "Category",
        null=True,
        blank=True,
        on_delete=models.SET_NULL
    )
    name = models.CharField(max_length=200, unique=True)
    brand = models.CharField(
        max_length=120,
        blank=True,
        help_text="Optional brand or maker shown on listings.",
    )
    sku = models.CharField(max_length=200, unique=True, null=True, blank=True)
    short_description = models.CharField(
        max_length=255,
        blank=True,
        help_text="Used on product listings and marketing widgets.",
    )
    description = models.TextField(verbose_name="Product Description")
    price = models.DecimalField(max_digits=10, decimal_places=2)
    rating = models.DecimalField(
        max_digits=4,
        decimal_places=2,
        null=True,
        blank=True
    )
    inventory_count = models.PositiveIntegerField(
        default=0,
        help_text="Current sellable stock for physical items.",
    )
    low_stock_threshold = models.PositiveIntegerField(
        default=5,
        help_text="Show a warning badge when stock is at or below this value.",
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Inactive products are hidden from the shop front.",
    )
    is_digital = models.BooleanField(
        default=False,
        help_text="Digital goods ignore stock tracking and always remain in stock.",
    )
    weight_grams = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Used to fine tune delivery estimates.",
    )
    created_on = models.DateTimeField(auto_now_add=True)
    updated_on = models.DateTimeField(auto_now=True)
    product_image = models.ImageField(null=True, blank=True)

    class Meta:
        verbose_name = "Product"
        verbose_name_plural = "Products"
        ordering = ['-created_on']

    def __str__(self):
        if self.brand:
            return f"{self.brand} - {self.name}"
        return self.name

    @property
    def is_in_stock(self):
        if self.is_digital:
            return True
        return self.inventory_count > 0

    @property
    def is_low_stock(self):
        if self.is_digital:
            return False
        return self.inventory_count <= self.low_stock_threshold

    def max_order_quantity(self):
        """Return the maximum quantity a customer can buy at once."""
        if self.is_digital:
            return None
        return max(self.inventory_count, 0)

    def adjust_inventory(self, quantity):
        """Increment or decrement inventory atomically."""
        if self.is_digital or quantity == 0:
            return

        Product.objects.filter(pk=self.pk).update(
            inventory_count=F('inventory_count') + quantity
        )
        Product.objects.filter(pk=self.pk, inventory_count__lt=0).update(
            inventory_count=0
        )
        self.refresh_from_db(fields=['inventory_count'])

    def can_fulfil_order(self, quantity):
        if self.is_digital:
            return True
        return self.inventory_count >= quantity

    def estimate_delivery_date(self):
        """Provide a rough delivery estimate for customer messaging."""
        if self.is_digital:
            return timezone.now().date()
        return timezone.now().date() + timedelta(days=4)
