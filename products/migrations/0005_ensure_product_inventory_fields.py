"""Ensure recently added product metadata columns exist for legacy databases."""

from django.db import migrations, models


def add_missing_fields(apps, schema_editor):
    Product = apps.get_model("products", "Product")
    table_name = Product._meta.db_table
    connection = schema_editor.connection

    with connection.cursor() as cursor:
        existing_columns = {
            column.name for column in connection.introspection.get_table_description(cursor, table_name)
        }

    def ensure_field(name, field):
        if name in existing_columns:
            return
        field.set_attributes_from_name(name)
        schema_editor.add_field(Product, field)

    ensure_field(
        "brand",
        models.CharField(
            max_length=120,
            blank=True,
            default="",
            help_text="Optional brand or maker shown on listings.",
        ),
    )
    ensure_field(
        "short_description",
        models.CharField(
            max_length=255,
            blank=True,
            default="",
            help_text="Used on product listings and marketing widgets.",
        ),
    )
    ensure_field(
        "inventory_count",
        models.PositiveIntegerField(
            default=0,
            help_text="Current sellable stock for physical items.",
        ),
    )
    ensure_field(
        "low_stock_threshold",
        models.PositiveIntegerField(
            default=5,
            help_text="Show a warning badge when stock is at or below this value.",
        ),
    )
    ensure_field(
        "is_active",
        models.BooleanField(
            default=True,
            help_text="Inactive products are hidden from the shop front.",
        ),
    )
    ensure_field(
        "is_digital",
        models.BooleanField(
            default=False,
            help_text="Digital goods ignore stock tracking and always remain in stock.",
        ),
    )
    ensure_field(
        "weight_grams",
        models.PositiveIntegerField(
            blank=True,
            null=True,
            help_text="Used to fine tune delivery estimates.",
        ),
    )


def remove_fields(apps, schema_editor):
    """Best effort rollback for databases that added the columns in this migration."""
    Product = apps.get_model("products", "Product")
    table_name = Product._meta.db_table
    connection = schema_editor.connection

    with connection.cursor() as cursor:
        existing_columns = {
            column.name for column in connection.introspection.get_table_description(cursor, table_name)
        }

    def drop_field(name):
        if name not in existing_columns:
            return
        field = Product._meta.get_field(name)
        schema_editor.remove_field(Product, field)

    # Drop in reverse order to respect potential constraints.
    for field_name in [
        "weight_grams",
        "is_digital",
        "is_active",
        "low_stock_threshold",
        "inventory_count",
        "short_description",
        "brand",
    ]:
        drop_field(field_name)


class Migration(migrations.Migration):

    dependencies = [
        ("products", "0003_alter_category_options_category_description_and_more"),
    ]

    operations = [
        migrations.RunPython(add_missing_fields, remove_fields),
    ]
