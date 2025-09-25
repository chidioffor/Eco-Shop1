from django import forms
from .models import Order


class OrderForm(forms.ModelForm):
    """
    Provides user-friendly placeholders, custom CSS classes,
    and autofocus to enhance the checkout user experience.
    """
    class Meta:
        model = Order
        fields = [
            'customer_name', 'email', 'phone_number',
            'address', 'city', 'postcode', 'county',
            'country', 'delivery_notes'
        ]

    def __init__(self, *args, **kwargs):
        """
        Initialize the form with placeholders, classes, and autofocus.
        """
        super().__init__(*args, **kwargs)
        self._set_placeholders_and_classes()

    def _set_placeholders_and_classes(self):
        """
        Apply placeholders, CSS classes, and other HTML attributes
        to each form field to improve the form's usability.
        """
        placeholders = {
            'customer_name': 'Customer Name',
            'email': 'Email Address',
            'phone_number': 'Phone Number',
            'address': 'Street Address',
            'city': 'City',
            'postcode': 'Postal or Zip Code',
            'county': 'County or State',
            'country': 'Country',
            'delivery_notes': 'Delivery instructions (optional)',
        }

        for field_name, field in self.fields.items():
            field.widget.attrs['class'] = 'stripe-style-input'
            field.label = False

            if field_name == 'customer_name':
                field.widget.attrs['autofocus'] = True

            placeholder = placeholders[field_name]
            if field.required:
                placeholder += ' *'
            field.widget.attrs['placeholder'] = placeholder

            if field_name == 'delivery_notes':
                field.widget.attrs['rows'] = 3
