from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import User, Product, Order, Cart, Review, Notification, Subscription, Category, Coupon, FarmerEarning


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    list_display = ['username', 'email', 'role', 'phone', 'is_active', 'date_joined']
    list_filter = ['role', 'is_active']
    fieldsets = UserAdmin.fieldsets + (
        ('Extra', {'fields': ('role', 'phone', 'address', 'is_available', 'current_lat', 'current_lng')}),
    )


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ['name', 'icon']


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ['name', 'farmer', 'category', 'price', 'stock', 'unit', 'is_active', 'created_at']
    list_filter = ['is_active', 'category']
    search_fields = ['name', 'farmer__username']


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ['id', 'customer', 'product', 'quantity', 'total_price', 'status', 'payment_method', 'payment_status', 'ordered_at']
    list_filter = ['status', 'payment_method', 'payment_status']
    search_fields = ['customer__username', 'product__name']


@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = ['customer', 'product', 'rating', 'created_at']
    list_filter = ['rating']


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ['user', 'title', 'is_read', 'created_at']
    list_filter = ['is_read']


@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    list_display = ['customer', 'product', 'quantity', 'frequency', 'is_active', 'next_order_date']
    list_filter = ['frequency', 'is_active']


@admin.register(Coupon)
class CouponAdmin(admin.ModelAdmin):
    list_display = ['code', 'discount_percent', 'min_order_amount', 'is_active', 'valid_until']
    list_filter = ['is_active']


@admin.register(FarmerEarning)
class FarmerEarningAdmin(admin.ModelAdmin):
    list_display = ['farmer', 'order', 'amount', 'platform_fee', 'net_amount', 'is_paid', 'created_at']
    list_filter = ['is_paid']
    search_fields = ['farmer__username']
