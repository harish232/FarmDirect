# 🌾 FarmDirect — Farmer Market App

A production-ready Django platform connecting farmers directly to customers.

## 👥 Roles
| Role | What they can do |
|------|-----------------|
| 🌾 **Farmer** | Add/edit products, manage orders, view earnings |
| 🛒 **Customer** | Browse, add to cart, apply coupons, order, track, review |
| 🚚 **Delivery Partner** | Accept deliveries, update live GPS location |
| 👑 **Admin** | Analytics dashboard, manage platform |

---

## ⚡ Setup (Local)

```bash
# 1. Clone and install
pip install -r requirements.txt

# 2. Configure environment
cp .env.example .env
# Edit .env — add DB credentials, Razorpay keys, email SMTP

# 3. Database
python manage.py migrate
python manage.py createsuperuser

# 4. Run
python manage.py runserver
```

---

## 🔑 Key API Endpoints

| Method | URL | Description |
|--------|-----|-------------|
| POST | `/api/token/` | Get auth token (mobile login) |
| GET  | `/api/products/` | List products |
| POST | `/api/cart/add/<pk>/` | Add to cart |
| POST | `/api/coupon/apply/` | Validate & apply coupon |
| POST | `/api/orders/place/` | Place order (supports coupon_code) |
| POST | `/api/razorpay/create-order/` | Create Razorpay payment order |
| POST | `/api/razorpay/verify/` | Verify Razorpay payment signature |
| GET  | `/api/farmer/earnings/` | Farmer earnings |
| GET  | `/api/notifications/` | Notifications |
| GET  | `/api/delivery/available/` | Available deliveries |
| GET  | `/api/admin/analytics/` | Admin stats + monthly revenue |

### Authentication
```
Authorization: Token <your-token>
```

---

## 💳 Razorpay Payment Flow

```
1. Customer clicks Pay
2. POST /api/razorpay/create-order/ → { razorpay_order_id, amount, key_id }
3. Open Razorpay checkout SDK on mobile/web
4. On success → POST /api/razorpay/verify/ with signature
5. Server verifies HMAC → marks orders as paid
```

---

## 🎟️ Coupon System

```
1. POST /api/coupon/apply/ { coupon_code, order_amount }
   → { valid, discount_percent, discount_amount, final_amount }
2. Pass coupon_code in POST /api/orders/place/
   → discount applied proportionally per item
```

---

## 🔄 Subscription Auto-Orders

Using **Celery + Redis**. Runs daily at 6 AM IST.

```bash
# Start Redis
redis-server

# Start Celery worker
celery -A farmermarket worker -l info

# Start Celery Beat (scheduler)
celery -A farmermarket beat -l info
```

---

## 🚀 Production Deploy (Ubuntu)

```bash
# Install system deps
sudo apt install python3-pip mysql-server redis-server nginx

# Collect static files
python manage.py collectstatic

# Run with gunicorn
gunicorn farmermarket.wsgi:application --bind 0.0.0.0:8000 --workers 3

# Nginx config: proxy_pass http://127.0.0.1:8000
# Set DEBUG=False and ALLOWED_HOSTS in .env
```

---

## 📱 Mobile App (React Native)
1. Use `/api/token/` to get token
2. Pass as `Authorization: Token <token>` header
3. All `/api/` endpoints are mobile-ready

---

## 💰 Revenue Model
- **10% platform commission** per delivered order (configurable in settings.py → `PLATFORM_FEE_PERCENT`)
- Farmer gets 90% net amount tracked in `FarmerEarning` model
- Razorpay for online payments (UPI, Card, Wallet)
