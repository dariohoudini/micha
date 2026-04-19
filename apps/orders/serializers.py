from rest_framework import serializers
from .models import Order, OrderItem, OrderStatusLog, Payment, Refund


class OrderItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = OrderItem
        fields = [
            'id', 'product', 'product_title', 'product_price',
            'quantity', 'subtotal', 'variant_info',
        ]
        read_only_fields = ['id', 'subtotal']


class OrderStatusLogSerializer(serializers.ModelSerializer):
    changed_by_email = serializers.ReadOnlyField(source='changed_by.email')

    class Meta:
        model = OrderStatusLog
        fields = ['id', 'old_status', 'new_status', 'note', 'changed_by_email', 'created_at']


class PaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Payment
        fields = [
            'id', 'amount', 'method', 'status',
            'gateway_reference', 'paid_at', 'created_at',
        ]
        read_only_fields = ['id', 'status', 'paid_at', 'created_at']


class RefundSerializer(serializers.ModelSerializer):
    class Meta:
        model = Refund
        fields = [
            'id', 'reason', 'amount', 'status',
            'admin_note', 'created_at', 'processed_at',
        ]
        read_only_fields = ['id', 'status', 'admin_note', 'created_at', 'processed_at']

    def create(self, validated_data):
        validated_data['requested_by'] = self.context['request'].user
        validated_data['order'] = self.context['order']
        return super().create(validated_data)


class OrderSerializer(serializers.ModelSerializer):
    items = OrderItemSerializer(many=True, read_only=True)
    status_logs = OrderStatusLogSerializer(many=True, read_only=True)
    payment = PaymentSerializer(read_only=True)
    buyer_email = serializers.ReadOnlyField(source='buyer.email')
    seller_email = serializers.ReadOnlyField(source='seller.email')

    class Meta:
        model = Order
        fields = [
            'id', 'buyer', 'buyer_email', 'seller', 'seller_email',
            'shipping_address', 'shipping_city', 'shipping_phone',
            'subtotal', 'shipping_cost', 'discount_amount', 'total',
            'coupon', 'status', 'payment_status',
            'tracking_number', 'carrier', 'estimated_delivery',
            'notes', 'cancelled_reason',
            'items', 'status_logs', 'payment',
            'created_at', 'updated_at', 'delivered_at',
        ]
        read_only_fields = [
            'id', 'buyer', 'subtotal', 'total',
            'payment_status', 'created_at', 'updated_at',
        ]


class UpdateOrderStatusSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=[
        'confirmed', 'processing', 'shipped', 'delivered', 'cancelled'
    ])
    note = serializers.CharField(required=False, allow_blank=True)
    tracking_number = serializers.CharField(required=False, allow_blank=True)
    carrier = serializers.CharField(required=False, allow_blank=True)
    estimated_delivery = serializers.DateField(required=False, allow_null=True)


class CheckoutSerializer(serializers.Serializer):
    shipping_address_id = serializers.IntegerField(required=False)
    shipping_address = serializers.CharField(required=False)
    shipping_city = serializers.CharField(required=False)
    shipping_phone = serializers.CharField(required=False)
    payment_method = serializers.ChoiceField(
        choices=['card', 'mobile_money', 'bank_transfer', 'cash']
    )
    coupon_code = serializers.CharField(required=False, allow_blank=True)
    notes = serializers.CharField(required=False, allow_blank=True)

    def validate(self, attrs):
        if not attrs.get('shipping_address_id') and not attrs.get('shipping_address'):
            raise serializers.ValidationError(
                "Provide either a saved address ID or a shipping address."
            )
        return attrs
