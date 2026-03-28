from django.contrib.auth import login, logout, authenticate
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Sum
from django.http import JsonResponse
from django.utils import timezone
from django.conf import settings
from decimal import Decimal


from .models import User, Product, Order, Cart, Review, Notification, FarmerEarning, Coupon, SupportTicket


def register_view(request):
    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        email = request.POST.get('email', '').strip()
        password = request.POST.get('password', '')
        role = request.POST.get('role', 'customer')
        phone = request.POST.get('phone', '')
        address = request.POST.get('address', '')

        # Validation checks
        if not username:
            messages.error(request, 'Username is required!')
            return redirect('register')
        if len(username) < 3:
            messages.error(request, 'Username must be at least 3 characters!')
            return redirect('register')
        if User.objects.filter(username__iexact=username).exists():
            messages.error(request, f'Username "{username}" is already taken. Please choose a different one.')
            return redirect('register')
        if not email or '@' not in email:
            messages.error(request, 'Please enter a valid email address!')
            return redirect('register')
        if User.objects.filter(email__iexact=email).exists():
            messages.error(request, 'An account with this email already exists. Try logging in instead.')
            return redirect('register')
        if len(password) < 6:
            messages.error(request, 'Password must be at least 6 characters!')
            return redirect('register')
        if role not in ['farmer', 'customer', 'delivery']:
            messages.error(request, 'Invalid role selected!')
            return redirect('register')

        try:
            # FIX: create user first, then set custom fields separately
            user = User.objects.create_user(
                username=username,
                email=email,
                password=password,
            )
            user.role = role
            user.phone = phone
            user.address = address
            user.save()

            login(request, user, backend='django.contrib.auth.backends.ModelBackend')
            messages.success(request, f'Welcome to FarmDirect, {username}!')
            return redirect('dashboard')
        except Exception as e:
            import traceback
            traceback.print_exc()  
            messages.error(request, f'Registration failed: {str(e)}')
            return redirect('register')

    return render(request, 'register.html')


def login_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
    if request.method == 'POST':
        username = request.POST.get('username', '')
        password = request.POST.get('password', '')
        user = authenticate(request, username=username, password=password)
        if user:
            login(request, user)
            return redirect('dashboard')
        else:
            messages.error(request, 'Wrong username or password!')
    return render(request, 'login.html')


def logout_view(request):
    logout(request)
    return redirect('login')


def dashboard_view(request):
    if not request.user.is_authenticated:
        return redirect('login')
    if request.user.is_farmer:
        products = Product.objects.filter(farmer=request.user, is_active=True)
        orders = Order.objects.filter(product__farmer=request.user).order_by('-ordered_at')[:5]
        earnings = FarmerEarning.objects.filter(farmer=request.user)
        total_earned = earnings.aggregate(total=Sum('net_amount'))['total'] or 0
        pending_payout = earnings.filter(is_paid=False).aggregate(total=Sum('net_amount'))['total'] or 0
        return render(request, 'farmer_dashboard.html', {
            'products': products, 'recent_orders': orders,
            'total_earned': total_earned, 'pending_payout': pending_payout,
            'total_products': products.count(),
            'total_orders': Order.objects.filter(product__farmer=request.user).count(),
        })
    elif request.user.is_admin_user or request.user.is_staff:
        return redirect('admin_dashboard')
    elif request.user.is_delivery:
        active_deliveries = Order.objects.filter(
            delivery_partner=request.user
        ).exclude(status__in=['delivered', 'cancelled']).order_by('-ordered_at')
        recent_delivered = Order.objects.filter(
            delivery_partner=request.user, status='delivered'
        ).order_by('-delivered_at')[:8]
        total_delivered = Order.objects.filter(
            delivery_partner=request.user, status='delivered'
        ).count()
        return render(request, 'delivery_dashboard.html', {
            'active_deliveries': active_deliveries,
            'recent_delivered': recent_delivered,
            'total_delivered': total_delivered,
            'total_earnings': 0,
        })
    else:
        orders = Order.objects.filter(customer=request.user).order_by('-ordered_at')[:5]
        cart_count = Cart.objects.filter(customer=request.user).count()
        unread = Notification.objects.filter(user=request.user, is_read=False).count()
        return render(request, 'customer_dashboard.html', {
            'recent_orders': orders, 'cart_count': cart_count, 'unread_notifications': unread,
        })


@login_required
def farmer_products(request):
    if not request.user.is_farmer:
        return redirect('dashboard')
    products = Product.objects.filter(farmer=request.user).order_by('-created_at')
    return render(request, 'farmer_products.html', {'products': products})


@login_required
def add_product(request):
    if not request.user.is_farmer:
        return redirect('dashboard')
    if request.method == 'POST':
        Product.objects.create(
            farmer=request.user,
            name=request.POST['name'],
            description=request.POST.get('description', ''),
            price=request.POST['price'],
            stock=request.POST['stock'],
            unit=request.POST.get('unit', 'kg'),
            image=request.FILES.get('image'),
        )
        messages.success(request, 'Product added successfully!')
        return redirect('farmer_products')
    return render(request, 'add_product.html')


@login_required
def edit_product(request, pk):
    if not request.user.is_farmer:
        return redirect('dashboard')
    product = get_object_or_404(Product, pk=pk, farmer=request.user)
    if request.method == 'POST':
        product.name = request.POST['name']
        product.description = request.POST.get('description', '')
        product.price = request.POST['price']
        product.stock = request.POST['stock']
        product.unit = request.POST.get('unit', 'kg')
        if 'image' in request.FILES:
            product.image = request.FILES['image']
        product.save()
        messages.success(request, 'Product updated!')
        return redirect('farmer_products')
    return render(request, 'edit_product.html', {'product': product})


@login_required
def delete_product(request, pk):
    if not request.user.is_farmer:
        return redirect('dashboard')
    product = get_object_or_404(Product, pk=pk, farmer=request.user)
    product.delete()
    messages.success(request, 'Product deleted!')
    return redirect('farmer_products')


@login_required
def farmer_orders(request):
    if not request.user.is_farmer:
        return redirect('dashboard')
    orders = Order.objects.filter(product__farmer=request.user).order_by('-ordered_at')
    return render(request, 'farmer_orders.html', {'orders': orders})


@login_required
def update_order_status(request, pk):
    if not request.user.is_farmer:
        return redirect('dashboard')
    order = get_object_or_404(Order, pk=pk, product__farmer=request.user)
    if request.method == 'POST':
        order.status = request.POST['status']
        if order.status == 'delivered':
            order.delivered_at = timezone.now()
            order.payment_status = 'paid'
        order.save()
        Notification.objects.create(
            user=order.customer, title='Order Update',
            message=f'Your order for {order.product.name} is now: {order.get_status_display()}.'
        )
        messages.success(request, 'Order status updated!')
    return redirect('farmer_orders')


@login_required
def farmer_earnings_view(request):
    if not request.user.is_farmer:
        return redirect('dashboard')
    earnings = FarmerEarning.objects.filter(farmer=request.user).order_by('-created_at')
    total_earned = earnings.aggregate(total=Sum('net_amount'))['total'] or 0
    pending_payout = earnings.filter(is_paid=False).aggregate(total=Sum('net_amount'))['total'] or 0
    return render(request, 'farmer_earnings.html', {
        'earnings': earnings, 'total_earned': total_earned, 'pending_payout': pending_payout,
    })


@login_required
def product_list(request):
    from .models import Category
    query = request.GET.get('q', '')
    category_id = request.GET.get('category', '')
    products = Product.objects.filter(stock__gt=0, is_active=True)
    if query:
        products = products.filter(name__icontains=query)
    if category_id:
        products = products.filter(category__id=category_id)
    categories = Category.objects.all()
    return render(request, 'product_list.html', {
        'products': products,
        'query': query,
        'categories': categories,
        'active_category': category_id,
    })


@login_required
def add_to_cart(request, pk):
    product = get_object_or_404(Product, pk=pk, is_active=True)
    if product.stock == 0:
        messages.error(request, f'{product.name} is out of stock!')
        return redirect('product_list')
    cart_item, created = Cart.objects.get_or_create(customer=request.user, product=product)
    if not created:
        if cart_item.quantity >= product.stock:
            messages.error(request, f'Only {product.stock} {product.unit} available!')
            return redirect('product_list')
        cart_item.quantity += 1
        cart_item.save()
    messages.success(request, f'{product.name} added to cart!')
    return redirect('product_list')


@login_required
def view_cart(request):
    cart_items = Cart.objects.filter(customer=request.user).select_related('product')
    subtotal = sum(item.total() for item in cart_items)
    discount = 0
    coupon_code = request.session.get('coupon_code', '')
    coupon_obj = None

    if coupon_code:
        try:
            coupon_obj = Coupon.objects.get(code=coupon_code, is_active=True)
            if subtotal >= coupon_obj.min_order_amount:
                discount = (subtotal * coupon_obj.discount_percent) / 100
        except Coupon.DoesNotExist:
            request.session.pop('coupon_code', None)

    total = subtotal - discount
    return render(request, 'cart.html', {
        'cart_items': cart_items,
        'subtotal': subtotal,
        'discount': round(discount, 2),
        'total': round(total, 2),
        'coupon_code': coupon_code,
        'coupon': coupon_obj,
    })


@login_required
def apply_coupon(request):
    if request.method == 'POST':
        code = request.POST.get('coupon_code', '').strip().upper()
        cart_items = Cart.objects.filter(customer=request.user)
        subtotal = sum(item.total() for item in cart_items)
        try:
            coupon = Coupon.objects.get(code=code, is_active=True)
            if subtotal < coupon.min_order_amount:
                messages.error(request, f'Minimum order Rs.{coupon.min_order_amount} needed for this coupon!')
            else:
                request.session['coupon_code'] = code
                messages.success(request, f'Coupon applied! {coupon.discount_percent}% off!')
        except Coupon.DoesNotExist:
            messages.error(request, 'Invalid or expired coupon!')
    return redirect('view_cart')


@login_required
def remove_coupon(request):
    request.session.pop('coupon_code', None)
    messages.info(request, 'Coupon removed.')
    return redirect('view_cart')


@login_required
def remove_from_cart(request, pk):
    cart_item = get_object_or_404(Cart, pk=pk, customer=request.user)
    cart_item.delete()
    messages.success(request, 'Item removed from cart!')
    return redirect('view_cart')


@login_required
def place_order(request):
    cart_items = Cart.objects.filter(customer=request.user)
    if not cart_items.exists():
        messages.error(request, 'Your cart is empty!')
        return redirect('view_cart')

    if request.method == 'POST':
        address = request.POST.get('address', '').strip()
        city = request.POST.get('city', '').strip()
        pincode = request.POST.get('pincode', '').strip()
        phone_number = request.POST.get('phone_number', '').strip()
        payment_method = request.POST.get('payment_method', 'cod')

        if not all([address, city, pincode, phone_number]):
            messages.error(request, 'Please fill all delivery details!')
            return redirect('view_cart')

        subtotal = sum(item.total() for item in cart_items)
        discount = 0
        coupon_code = request.session.get('coupon_code', '')
        if coupon_code:
            try:
                coupon = Coupon.objects.get(code=coupon_code, is_active=True)
                if subtotal >= coupon.min_order_amount:
                    discount = (subtotal * coupon.discount_percent) / 100
            except Coupon.DoesNotExist:
                pass

        platform_fee_pct = Decimal(str(getattr(settings, 'PLATFORM_FEE_PERCENT', 10))) / Decimal('100')

        for item in cart_items:
            if item.quantity > item.product.stock:
                messages.error(request, f'Only {item.product.stock} {item.product.unit} left for {item.product.name}')
                return redirect('view_cart')

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
                message=f'New order: {item.product.name} x{item.quantity} from {request.user.username}.'
            )

        cart_items.delete()
        request.session.pop('coupon_code', None)
        messages.success(request, 'Order placed successfully!')
        return redirect('my_orders')

    return redirect('view_cart')


@login_required
def my_orders(request):
    orders = Order.objects.filter(customer=request.user).order_by('-ordered_at')
    return render(request, 'my_orders.html', {'orders': orders})


@login_required
def add_review_view(request, order_pk):
    order = get_object_or_404(Order, pk=order_pk, customer=request.user, status='delivered')
    if request.method == 'POST':
        Review.objects.update_or_create(
            product=order.product, customer=request.user,
            defaults={
                'rating': int(request.POST.get('rating', 5)),
                'comment': request.POST.get('comment', '')
            }
        )
        messages.success(request, 'Review submitted!')
    return redirect('my_orders')


@login_required
def admin_dashboard_view(request):
    if not (request.user.is_admin_user or request.user.is_staff):
        return redirect('dashboard')
    total_orders = Order.objects.count()
    total_revenue = Order.objects.filter(status='delivered').aggregate(total=Sum('total_price'))['total'] or 0
    total_farmers = User.objects.filter(role='farmer').count()
    total_customers = User.objects.filter(role='customer').count()
    pending_orders = Order.objects.filter(status='pending').count()
    recent_orders = Order.objects.select_related('customer', 'product').order_by('-ordered_at')[:20]
    return render(request, 'admin_dashboard.html', {
        'total_orders': total_orders, 'total_revenue': total_revenue,
        'total_farmers': total_farmers, 'total_customers': total_customers,
        'pending_orders': pending_orders, 'recent_orders': recent_orders,
    })


@login_required
def profile_view(request):
    return render(request, 'profile.html', {'user': request.user})


@login_required
def edit_profile_view(request):
    user = request.user
    if request.method == 'POST':
        user.first_name = request.POST.get('first_name', '').strip()
        user.last_name  = request.POST.get('last_name', '').strip()
        user.email      = request.POST.get('email', '').strip()
        user.phone      = request.POST.get('phone', '').strip()
        user.address    = request.POST.get('address', '').strip()
        user.bio        = request.POST.get('bio', '').strip()
        if 'profile_pic' in request.FILES:
            user.profile_pic = request.FILES['profile_pic']
        user.save()
        messages.success(request, 'Profile updated successfully!')
        return redirect('profile')
    return render(request, 'edit_profile.html', {'user': user})


@login_required
def settings_view(request):
    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'change_password':
            old_pw  = request.POST.get('old_password', '')
            new_pw  = request.POST.get('new_password', '')
            confirm = request.POST.get('confirm_password', '')
            if not request.user.check_password(old_pw):
                messages.error(request, 'Current password is incorrect.')
            elif len(new_pw) < 6:
                messages.error(request, 'New password must be at least 6 characters.')
            elif new_pw != confirm:
                messages.error(request, 'Passwords do not match.')
            else:
                request.user.set_password(new_pw)
                request.user.save()
                messages.success(request, 'Password changed! Please log in again.')
                return redirect('login')
    return render(request, 'settings.html')


@login_required
def support_view(request):
    tickets = SupportTicket.objects.filter(user=request.user)
    if request.method == 'POST':
        subject  = request.POST.get('subject', '').strip()
        message  = request.POST.get('message', '').strip()
        category = request.POST.get('category', 'other')
        if subject and message:
            SupportTicket.objects.create(
                user=request.user, subject=subject,
                message=message, category=category
            )
            messages.success(request, 'Support ticket submitted! We will get back to you within 24 hours.')
            return redirect('support')
        else:
            messages.error(request, 'Please fill in all fields.')
    return render(request, 'support.html', {'tickets': tickets})


def about_view(request):
    return render(request, 'about.html')