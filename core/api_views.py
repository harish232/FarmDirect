import hmac
import hashlib
import razorpay
from django.conf import settings
from rest_framework.decorators import api_view, permission_classes, parser_classes
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from rest_framework.response import Response
from rest_framework import status
from django.db.models import Sum, Count, Q
from django.utils import timezone
from .models import Product, Order, Cart, Review, Notification, Subscription, Category, FarmerEarning, User, Coupon
from .serializers import (ProductSerializer, OrderSerializer, CartSerializer,
                          ReviewSerializer, NotificationSerializer, SubscriptionSerializer,
                          CategorySerializer, FarmerEarningSerializer, UserSerializer)


# ─── Auth / Profile ──────────────────────────────────────────────────────────

@api_view(['GET', 'PUT'])
@permission_classes([IsAuthenticated])
def api_profile(request):
    if request.method == 'GET':
        serializer = UserSerializer(request.user)
        return Response(serializer.data)
    serializer = UserSerializer(request.user, data=request.data, partial=True)
    if serializer.is_valid():
        serializer.save()
        return Response(serializer.data)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


# ─── Categories ──────────────────────────────────────────────────────────────

@api_view(['GET'])
@permission_classes([AllowAny])
def api_categories(request):
    categories = Category.objects.all()
    serializer = CategorySerializer(categories, many=True)
    return Response(serializer.data)


# ─── Products ────────────────────────────────────────────────────────────────

@api_view(['GET'])
@permission_classes([AllowAny])
def api_products(request):
    products = Product.objects.filter(stock__gt=0, is_active=True)
    query = request.GET.get('q', '')
    category = request.GET.get('category', '')
    farmer_id = request.GET.get('farmer', '')
    if query:
        products = products.filter(name__icontains=query)
    if category:
        products = products.filter(category__id=category)
    if farmer_id:
        products = products.filter(farmer__id=farmer_id)
    serializer = ProductSerializer(products, many=True, context={'request': request})
    return Response({'count': products.count(), 'products': serializer.data})


@api_view(['GET'])
@permission_classes([AllowAny])
def api_product_detail(request, pk):
    try:
        product = Product.objects.get(pk=pk)
    except Product.DoesNotExist:
        return Response({'error': 'Product not found!'}, status=status.HTTP_404_NOT_FOUND)
    serializer = ProductSerializer(product, context={'request': request})
    return Response(serializer.data)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
@parser_classes([MultiPartParser, FormParser, JSONParser])
def api_add_product(request):
    if not request.user.is_farmer:
        return Response({'error': 'Only farmers can add products!'}, status=status.HTTP_403_FORBIDDEN)
    serializer = ProductSerializer(data=request.data)
    if serializer.is_valid():
        serializer.save(farmer=request.user)
        return Response({'message': 'Product added!', 'product': serializer.data}, status=status.HTTP_201_CREATED)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['PUT'])
@permission_classes([IsAuthenticated])
@parser_classes([MultiPartParser, FormParser, JSONParser])
def api_edit_product(request, pk):
    try:
        product = Product.objects.get(pk=pk, farmer=request.user)
    except Product.DoesNotExist:
        return Response({'error': 'Product not found!'}, status=status.HTTP_404_NOT_FOUND)
    serializer = ProductSerializer(product, data=request.data, partial=True)
    if serializer.is_valid():
        serializer.save()
        return Response({'message': 'Product updated!', 'product': serializer.data})
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
def api_delete_product(request, pk):
    try:
        product = Product.objects.get(pk=pk, farmer=request.user)
    except Product.DoesNotExist:
        return Response({'error': 'Product not found!'}, status=status.HTTP_404_NOT_FOUND)
    product.delete()
    return Response({'message': 'Product deleted!'}, status=status.HTTP_204_NO_CONTENT)


# ─── Orders ──────────────────────────────────────────────────────────────────

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def api_my_orders(request):
    if request.user.is_farmer:
        orders = Order.objects.filter(product__farmer=request.user).order_by('-ordered_at')
    elif request.user.is_delivery():
        orders = Order.objects.filter(delivery_partner=request.user).order_by('-ordered_at')
    else:
        orders = Order.objects.filter(customer=request.user).order_by('-ordered_at')
    serializer = OrderSerializer(orders, many=True)
    return Response({'count': orders.count(), 'orders': serializer.data})


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def api_place_order(request):
    if request.user.is_farmer:
        return Response({'error': 'Farmers cannot place orders!'}, status=status.HTTP_403_FORBIDDEN)

    cart_items = Cart.objects.filter(customer=request.user)
    if not cart_items.exists():
        return Response({'error': 'Cart is empty!'}, status=status.HTTP_400_BAD_REQUEST)

    address = request.data.get('address', '')
    city = request.data.get('city', '')
    pincode = request.data.get('pincode', '')
    phone_number = request.data.get('phone_number', '')
    payment_method = request.data.get('payment_method', 'cod')

    if not all([address, city, pincode, phone_number]):
        return Response({'error': 'Address, city, pincode and phone are required!'}, status=status.HTTP_400_BAD_REQUEST)

    # ✅ NEW: Coupon support in API
    subtotal = sum(item.total() for item in cart_items)
    discount = 0
    coupon_code = request.data.get('coupon_code', '').strip().upper()
    if coupon_code:
        try:
            coupon = Coupon.objects.get(code=coupon_code, is_active=True)
            if subtotal >= coupon.min_order_amount:
                discount = (subtotal * coupon.discount_percent) / 100
        except Coupon.DoesNotExist:
            return Response({'error': f'Invalid coupon: {coupon_code}'}, status=status.HTTP_400_BAD_REQUEST)

    platform_fee_pct = getattr(settings, 'PLATFORM_FEE_PERCENT', 10) / 100
    orders_created = []

    for item in cart_items:
        if item.quantity > item.product.stock:
            return Response({'error': f'Only {item.product.stock} {item.product.unit} available for {item.product.name}'},
                            status=status.HTTP_400_BAD_REQUEST)

        item_total = item.total()
        item_discount = (item_total / subtotal) * discount if subtotal > 0 else 0
        final_price = round(item_total - item_discount, 2)

        order = Order.objects.create(
            customer=request.user, product=item.product,
            quantity=item.quantity, total_price=final_price,
            address=address, city=city, pincode=pincode,
            phone_number=phone_number, payment_method=payment_method,
        )
        item.product.stock -= item.quantity
        item.product.save()

        platform_fee = order.total_price * platform_fee_pct
        FarmerEarning.objects.create(
            farmer=item.product.farmer, order=order,
            amount=order.total_price, platform_fee=platform_fee,
            net_amount=order.total_price - platform_fee,
        )
        Notification.objects.create(
            user=item.product.farmer, title='New Order!',
            message=f'You received an order for {item.product.name} x{item.quantity} from {request.user.username}.'
        )
        orders_created.append(order)

    cart_items.delete()
    serializer = OrderSerializer(orders_created, many=True)
    return Response({'message': 'Order placed successfully!', 'orders': serializer.data}, status=status.HTTP_201_CREATED)


@api_view(['PATCH'])
@permission_classes([IsAuthenticated])
def api_update_order(request, pk):
    if request.user.is_farmer:
        try:
            order = Order.objects.get(pk=pk, product__farmer=request.user)
        except Order.DoesNotExist:
            return Response({'error': 'Order not found!'}, status=status.HTTP_404_NOT_FOUND)
    elif request.user.is_delivery():
        try:
            order = Order.objects.get(pk=pk, delivery_partner=request.user)
        except Order.DoesNotExist:
            return Response({'error': 'Order not found!'}, status=status.HTTP_404_NOT_FOUND)
    else:
        return Response({'error': 'Not authorized!'}, status=status.HTTP_403_FORBIDDEN)

    new_status = request.data.get('status', order.status)
    order.status = new_status
    if new_status == 'delivered':
        order.delivered_at = timezone.now()
        order.payment_status = 'paid'
    order.save()

    Notification.objects.create(
        user=order.customer, title='Order Update',
        message=f'Your order for {order.product.name} is now: {new_status}.'
    )
    return Response({'message': 'Order status updated!', 'status': order.status})


# ─── Cart ─────────────────────────────────────────────────────────────────────

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def api_cart(request):
    cart_items = Cart.objects.filter(customer=request.user)
    serializer = CartSerializer(cart_items, many=True, context={'request': request})
    total = sum(item.total() for item in cart_items)
    return Response({'cart_items': serializer.data, 'total': total, 'count': cart_items.count()})


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def api_add_to_cart(request, pk):
    try:
        product = Product.objects.get(pk=pk, is_active=True)
    except Product.DoesNotExist:
        return Response({'error': 'Product not found!'}, status=status.HTTP_404_NOT_FOUND)

    if product.stock == 0:
        return Response({'error': 'Product out of stock!'}, status=status.HTTP_400_BAD_REQUEST)

    cart_item, created = Cart.objects.get_or_create(customer=request.user, product=product)
    if not created:
        if cart_item.quantity >= product.stock:
            return Response({'error': f'Only {product.stock} {product.unit} available!'}, status=status.HTTP_400_BAD_REQUEST)
        cart_item.quantity += 1
        cart_item.save()

    return Response({'message': f'{product.name} added to cart!', 'quantity': cart_item.quantity})


@api_view(['PATCH'])
@permission_classes([IsAuthenticated])
def api_update_cart_item(request, pk):
    try:
        cart_item = Cart.objects.get(pk=pk, customer=request.user)
    except Cart.DoesNotExist:
        return Response({'error': 'Cart item not found!'}, status=status.HTTP_404_NOT_FOUND)
    quantity = request.data.get('quantity', cart_item.quantity)
    if quantity < 1:
        cart_item.delete()
        return Response({'message': 'Item removed from cart!'})
    if quantity > cart_item.product.stock:
        return Response({'error': f'Only {cart_item.product.stock} available!'}, status=status.HTTP_400_BAD_REQUEST)
    cart_item.quantity = quantity
    cart_item.save()
    return Response({'message': 'Cart updated!', 'quantity': cart_item.quantity})


@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
def api_remove_from_cart(request, pk):
    try:
        cart_item = Cart.objects.get(pk=pk, customer=request.user)
    except Cart.DoesNotExist:
        return Response({'error': 'Cart item not found!'}, status=status.HTTP_404_NOT_FOUND)
    cart_item.delete()
    return Response({'message': 'Item removed from cart!'})


# ─── Coupon ───────────────────────────────────────────────────────────────────

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def api_apply_coupon(request):
    """✅ NEW: Validate coupon and return discount info"""
    code = request.data.get('coupon_code', '').strip().upper()
    order_amount = request.data.get('order_amount', 0)

    try:
        coupon = Coupon.objects.get(code=code, is_active=True)
    except Coupon.DoesNotExist:
        return Response({'valid': False, 'error': 'Invalid or expired coupon!'}, status=status.HTTP_400_BAD_REQUEST)

    if float(order_amount) < float(coupon.min_order_amount):
        return Response({
            'valid': False,
            'error': f'Minimum order Rs.{coupon.min_order_amount} required!'
        }, status=status.HTTP_400_BAD_REQUEST)

    discount = (float(order_amount) * coupon.discount_percent) / 100
    return Response({
        'valid': True,
        'coupon_code': coupon.code,
        'discount_percent': coupon.discount_percent,
        'discount_amount': round(discount, 2),
        'final_amount': round(float(order_amount) - discount, 2),
    })


# ─── Reviews ─────────────────────────────────────────────────────────────────

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def api_add_review(request, product_pk):
    if not request.user.is_customer:
        return Response({'error': 'Only customers can review!'}, status=status.HTTP_403_FORBIDDEN)
    try:
        product = Product.objects.get(pk=product_pk)
    except Product.DoesNotExist:
        return Response({'error': 'Product not found!'}, status=status.HTTP_404_NOT_FOUND)

    has_ordered = Order.objects.filter(customer=request.user, product=product, status='delivered').exists()
    if not has_ordered:
        return Response({'error': 'You can only review products you have received!'}, status=status.HTTP_403_FORBIDDEN)

    review, created = Review.objects.get_or_create(
        product=product, customer=request.user,
        defaults={'rating': request.data.get('rating', 5), 'comment': request.data.get('comment', '')}
    )
    if not created:
        review.rating = request.data.get('rating', review.rating)
        review.comment = request.data.get('comment', review.comment)
        review.save()

    serializer = ReviewSerializer(review)
    return Response({'message': 'Review saved!', 'review': serializer.data}, status=status.HTTP_201_CREATED)


# ─── Notifications ────────────────────────────────────────────────────────────

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def api_notifications(request):
    notifications = Notification.objects.filter(user=request.user).order_by('-created_at')
    unread_count = notifications.filter(is_read=False).count()
    serializer = NotificationSerializer(notifications[:50], many=True)
    return Response({'unread_count': unread_count, 'notifications': serializer.data})


@api_view(['PATCH'])
@permission_classes([IsAuthenticated])
def api_mark_notifications_read(request):
    Notification.objects.filter(user=request.user, is_read=False).update(is_read=True)
    return Response({'message': 'All notifications marked as read!'})


# ─── Subscriptions ────────────────────────────────────────────────────────────

@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def api_subscriptions(request):
    if request.method == 'GET':
        subs = Subscription.objects.filter(customer=request.user, is_active=True)
        serializer = SubscriptionSerializer(subs, many=True)
        return Response(serializer.data)

    try:
        product = Product.objects.get(pk=request.data.get('product_id'))
    except Product.DoesNotExist:
        return Response({'error': 'Product not found!'}, status=status.HTTP_404_NOT_FOUND)

    sub = Subscription.objects.create(
        customer=request.user, product=product,
        quantity=request.data.get('quantity', 1),
        frequency=request.data.get('frequency', 'weekly'),
    )
    serializer = SubscriptionSerializer(sub)
    return Response({'message': 'Subscription created!', 'subscription': serializer.data}, status=status.HTTP_201_CREATED)


@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
def api_cancel_subscription(request, pk):
    try:
        sub = Subscription.objects.get(pk=pk, customer=request.user)
    except Subscription.DoesNotExist:
        return Response({'error': 'Subscription not found!'}, status=status.HTTP_404_NOT_FOUND)
    sub.is_active = False
    sub.save()
    return Response({'message': 'Subscription cancelled!'})


# ─── Farmer Earnings ─────────────────────────────────────────────────────────

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def api_farmer_earnings(request):
    if not request.user.is_farmer:
        return Response({'error': 'Only farmers can view earnings!'}, status=status.HTTP_403_FORBIDDEN)
    earnings = FarmerEarning.objects.filter(farmer=request.user).order_by('-created_at')
    total_earned = earnings.aggregate(total=Sum('net_amount'))['total'] or 0
    total_pending = earnings.filter(is_paid=False).aggregate(total=Sum('net_amount'))['total'] or 0
    serializer = FarmerEarningSerializer(earnings, many=True)
    return Response({
        'total_earned': total_earned,
        'pending_payout': total_pending,
        'earnings': serializer.data
    })


# ─── Delivery Partner ─────────────────────────────────────────────────────────

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def api_available_deliveries(request):
    if not request.user.is_delivery():
        return Response({'error': 'Only delivery partners!'}, status=status.HTTP_403_FORBIDDEN)
    orders = Order.objects.filter(status='packed', delivery_partner__isnull=True).order_by('ordered_at')
    serializer = OrderSerializer(orders, many=True)
    return Response({'orders': serializer.data})


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def api_accept_delivery(request, pk):
    if not request.user.is_delivery():
        return Response({'error': 'Only delivery partners!'}, status=status.HTTP_403_FORBIDDEN)
    try:
        order = Order.objects.get(pk=pk, status='packed', delivery_partner__isnull=True)
    except Order.DoesNotExist:
        return Response({'error': 'Order not available!'}, status=status.HTTP_404_NOT_FOUND)
    order.delivery_partner = request.user
    order.status = 'picked_up'
    order.save()
    Notification.objects.create(
        user=order.customer, title='Order Picked Up!',
        message=f'Your order is picked up by {request.user.username} and on the way!'
    )
    return Response({'message': 'Delivery accepted!', 'order_id': order.id})


@api_view(['PATCH'])
@permission_classes([IsAuthenticated])
def api_update_location(request):
    if not request.user.is_delivery():
        return Response({'error': 'Only delivery partners!'}, status=status.HTTP_403_FORBIDDEN)
    request.user.current_lat = request.data.get('lat', request.user.current_lat)
    request.user.current_lng = request.data.get('lng', request.user.current_lng)
    request.user.save()
    return Response({'message': 'Location updated!'})


# ─── Razorpay Payment ─────────────────────────────────────────────────────────

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def api_razorpay_create_order(request):
    """✅ NEW: Create a Razorpay order before payment"""
    amount = request.data.get('amount')
    if not amount:
        return Response({'error': 'Amount is required!'}, status=status.HTTP_400_BAD_REQUEST)

    try:
        client = razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))
        razorpay_order = client.order.create({
            'amount': int(float(amount) * 100),  # Convert to paise
            'currency': 'INR',
            'payment_capture': 1,
        })
        return Response({
            'razorpay_order_id': razorpay_order['id'],
            'amount': razorpay_order['amount'],
            'currency': razorpay_order['currency'],
            'key_id': settings.RAZORPAY_KEY_ID,
        })
    except Exception as e:
        return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def api_razorpay_verify(request):
    """✅ NEW: Verify Razorpay payment signature and mark order as paid"""
    razorpay_order_id = request.data.get('razorpay_order_id')
    razorpay_payment_id = request.data.get('razorpay_payment_id')
    razorpay_signature = request.data.get('razorpay_signature')
    order_ids = request.data.get('order_ids', [])  # Django Order IDs to mark paid

    if not all([razorpay_order_id, razorpay_payment_id, razorpay_signature]):
        return Response({'error': 'Missing payment details!'}, status=status.HTTP_400_BAD_REQUEST)

    # Verify HMAC signature
    message = f'{razorpay_order_id}|{razorpay_payment_id}'
    expected_signature = hmac.new(
        settings.RAZORPAY_KEY_SECRET.encode(),
        message.encode(),
        hashlib.sha256
    ).hexdigest()

    if expected_signature != razorpay_signature:
        return Response({'error': 'Invalid payment signature! Payment verification failed.'}, status=status.HTTP_400_BAD_REQUEST)

    # Mark orders as paid
    updated = Order.objects.filter(
        id__in=order_ids, customer=request.user
    ).update(
        payment_status='paid',
        razorpay_order_id=razorpay_order_id,
        razorpay_payment_id=razorpay_payment_id,
    )

    Notification.objects.create(
        user=request.user, title='Payment Successful!',
        message=f'Payment of Rs.{request.data.get("amount", "")} confirmed via Razorpay.'
    )

    return Response({
        'message': 'Payment verified successfully!',
        'orders_updated': updated,
        'razorpay_payment_id': razorpay_payment_id,
    })


# ─── Admin Analytics ─────────────────────────────────────────────────────────

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def api_admin_analytics(request):
    if not (request.user.is_admin_user or request.user.is_staff):
        return Response({'error': 'Admin only!'}, status=status.HTTP_403_FORBIDDEN)
    total_orders = Order.objects.count()
    total_revenue = Order.objects.filter(status='delivered').aggregate(total=Sum('total_price'))['total'] or 0
    total_farmers = User.objects.filter(role='farmer').count()
    total_customers = User.objects.filter(role='customer').count()
    total_products = Product.objects.filter(is_active=True).count()
    pending_orders = Order.objects.filter(status='pending').count()

    # ✅ NEW: Monthly revenue breakdown
    from django.db.models.functions import TruncMonth
    monthly_revenue = (
        Order.objects.filter(status='delivered')
        .annotate(month=TruncMonth('ordered_at'))
        .values('month')
        .annotate(revenue=Sum('total_price'))
        .order_by('-month')[:6]
    )

    return Response({
        'total_orders': total_orders,
        'total_revenue': total_revenue,
        'total_farmers': total_farmers,
        'total_customers': total_customers,
        'total_products': total_products,
        'pending_orders': pending_orders,
        'monthly_revenue': list(monthly_revenue),
    })
