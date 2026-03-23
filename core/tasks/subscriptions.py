"""
Subscription Auto-Order Task
Run via Celery Beat — set to execute daily.
"""
from celery import shared_task
from django.utils import timezone
from datetime import timedelta
from ..models import Subscription, Order, Cart, FarmerEarning, Notification
from django.conf import settings


@shared_task
def process_subscription_orders():
    """
    Runs daily. Creates orders for subscriptions whose next_order_date is today.
    """
    today = timezone.now().date()
    due_subs = Subscription.objects.filter(
        is_active=True,
        next_order_date__lte=today,
    ).select_related('customer', 'product', 'product__farmer')

    created_count = 0
    platform_fee_pct = getattr(settings, 'PLATFORM_FEE_PERCENT', 10) / 100

    for sub in due_subs:
        product = sub.product
        customer = sub.customer

        # Skip if not enough stock
        if product.stock < sub.quantity:
            Notification.objects.create(
                user=customer,
                title='Subscription Paused',
                message=f'{product.name} is out of stock. Your subscription will retry next cycle.'
            )
            continue

        total_price = product.price * sub.quantity
        order = Order.objects.create(
            customer=customer,
            product=product,
            quantity=sub.quantity,
            total_price=total_price,
            address=customer.address,
            city='',
            pincode='',
            phone_number=customer.phone,
            payment_method='cod',
        )
        product.stock -= sub.quantity
        product.save()

        platform_fee = total_price * platform_fee_pct
        FarmerEarning.objects.create(
            farmer=product.farmer, order=order,
            amount=total_price, platform_fee=platform_fee,
            net_amount=total_price - platform_fee,
        )

        # Notify customer and farmer
        Notification.objects.create(
            user=customer,
            title='Subscription Order Placed!',
            message=f'Auto-order: {sub.quantity} {product.unit} of {product.name} placed successfully.'
        )
        Notification.objects.create(
            user=product.farmer,
            title='Subscription Order!',
            message=f'Auto-order from {customer.username}: {product.name} x{sub.quantity}.'
        )

        # Advance next_order_date
        if sub.frequency == 'weekly':
            sub.next_order_date = today + timedelta(weeks=1)
        elif sub.frequency == 'biweekly':
            sub.next_order_date = today + timedelta(weeks=2)
        elif sub.frequency == 'monthly':
            sub.next_order_date = today + timedelta(days=30)
        sub.save()

        created_count += 1

    return f'Processed {created_count} subscription orders.'
