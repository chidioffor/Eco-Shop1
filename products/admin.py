from django.contrib import admin
from .models import Product, Category

# Register your models here.


class ProductAdmin(admin.ModelAdmin):
    list_display = (
        'category',
        'name',
        'brand',
        'price',
        'sku',
        'rating',
        'inventory_count',
        'is_active',
        'created_on',
        'updated_on',
        'product_image',
    )
    ordering = ('-created_on',)

    list_filter = (
        'category', 'rating', 'is_active', 'is_digital', 'created_on'
    )
    search_fields = (
        'name', 'brand', 'sku', 'category__name', 'short_description'
    )
    list_editable = ('inventory_count', 'is_active')


class CategoryAdmin(admin.ModelAdmin):
    list_display = (
        'name',
        'friendly_name',
        'display_order',
    )
    list_editable = ('display_order',)
    search_fields = ('name', 'friendly_name', 'slug')
    prepopulated_fields = {'slug': ('name',)}


admin.site.register(Product, ProductAdmin)
admin.site.register(Category, CategoryAdmin)
