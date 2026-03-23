from rest_framework import serializers
from .models import User, Product, Order, Cart, Review, Notification, Subscription, Category, FarmerEarning


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'role', 'phone', 'address', 'is_available']


class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ['id', 'name', 'icon']


class ReviewSerializer(serializers.ModelSerializer):
    customer_name = serializers.CharField(source='customer.username', read_only=True)

    class Meta:
        model = Review
        fields = ['id', 'customer_name', 'rating', 'comment', 'created_at']


class ProductSerializer(serializers.ModelSerializer):
    farmer_name = serializers.CharField(source='farmer.username', read_only=True)
    farmer_phone = serializers.CharField(source='farmer.phone', read_only=True)
    category_name = serializers.CharField(source='category.name', read_only=True)
    average_rating = serializers.FloatField(read_only=True)
    reviews = ReviewSerializer(many=True, read_only=True)

    class Meta:
        model = Product
        fields = ['id', 'name', 'description', 'price', 'stock', 'unit', 'image',
                  'farmer_name', 'farmer_phone', 'category_name', 'average_rating',
                  'reviews', 'is_active', 'created_at']


class OrderSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source='product.name', read_only=True)
    customer_name = serializers.CharField(source='customer.username', read_only=True)
    delivery_partner_name = serializers.CharField(source='delivery_partner.username', read_only=True)

    class Meta:
        model = Order
        fields = ['id', 'product_name', 'customer_name', 'delivery_partner_name',
                  'quantity', 'total_price', 'status', 'address', 'city', 'pincode',
                  'phone_number', 'payment_method', 'payment_status',
                  'ordered_at', 'delivered_at']


class CartSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source='product.name', read_only=True)
    product_price = serializers.DecimalField(source='product.price', max_digits=10, decimal_places=2, read_only=True)
    product_unit = serializers.CharField(source='product.unit', read_only=True)
    product_image = serializers.ImageField(source='product.image', read_only=True)
    total = serializers.SerializerMethodField()

    class Meta:
        model = Cart
        fields = ['id', 'product_name', 'product_price', 'product_unit', 'product_image', 'quantity', 'total']

    def get_total(self, obj):
        return obj.total()


class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = ['id', 'title', 'message', 'is_read', 'created_at']


class SubscriptionSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source='product.name', read_only=True)

    class Meta:
        model = Subscription
        fields = ['id', 'product_name', 'quantity', 'frequency', 'is_active', 'next_order_date', 'created_at']


class FarmerEarningSerializer(serializers.ModelSerializer):
    order_id = serializers.IntegerField(source='order.id', read_only=True)
    product_name = serializers.CharField(source='order.product.name', read_only=True)

    class Meta:
        model = FarmerEarning
        fields = ['id', 'order_id', 'product_name', 'amount', 'platform_fee', 'net_amount', 'is_paid', 'created_at']
