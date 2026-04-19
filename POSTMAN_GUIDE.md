# MICHA — Postman Testing Guide

## Setup

1. Import this collection into Postman
2. Set base URL variable: `{{base}}` = `http://127.0.0.1:8000`
3. Set `{{token}}` after logging in (see Auth section)

---

## 1. AUTH

### Register buyer
POST {{base}}/api/auth/register/
```json
{
  "email": "buyer@test.com",
  "password": "Test1234!",
  "password2": "Test1234!",
  "account_type": "buyer",
  "full_name": "João Silva"
}
```
Expected: 201 — check email in terminal for OTP

### Verify email
POST {{base}}/api/auth/verify-email/
```json
{ "email": "buyer@test.com", "otp": "123456" }
```
Expected: 200

### Login → copy access token
POST {{base}}/api/auth/login/
```json
{ "email": "buyer@test.com", "password": "Test1234!" }
```
Expected: 200 — copy `access` into `{{token}}`

### Profile
GET {{base}}/api/auth/profile/
Header: Authorization: Bearer {{token}}
Expected: 200 with user data

### Logout
POST {{base}}/api/auth/logout/
Header: Authorization: Bearer {{token}}
```json
{ "refresh": "<your_refresh_token>" }
```

### Forgot password
POST {{base}}/api/auth/forgot-password/
```json
{ "email": "buyer@test.com" }
```

### Referral info
GET {{base}}/api/auth/referral/
Header: Authorization: Bearer {{token}}

### Loyalty points
GET {{base}}/api/auth/loyalty/
Header: Authorization: Bearer {{token}}

### Redeem points
POST {{base}}/api/auth/loyalty/redeem/
```json
{ "points": 100 }
```

---

## 2. SELLER FLOW

### Register seller
POST {{base}}/api/auth/register/
```json
{
  "email": "seller@test.com",
  "password": "Test1234!",
  "password2": "Test1234!",
  "account_type": "seller"
}
```

### Seller dashboard
GET {{base}}/api/seller/dashboard/
Header: Authorization: Bearer {{seller_token}}
Expected: 200 with stats + onboarding checklist

### Toggle holiday mode
POST {{base}}/api/seller/holiday/
```json
{ "message": "Back on Monday!" }
```

### Create store (via stores endpoint)
POST {{base}}/api/stores/
```json
{
  "name": "My Test Store",
  "city": "Luanda",
  "description": "Best seller in Angola"
}
```

---

## 3. PRODUCTS

### List products (public)
GET {{base}}/api/products/
Expected: 200 — paginated list

### Search
GET {{base}}/api/products/?search=Samsung

### Filter by category
GET {{base}}/api/products/?category=Electronics

### Price range
GET {{base}}/api/products/?min_price=10000&max_price=100000

### Filter by condition
GET {{base}}/api/products/?condition=new

### Filter by city
GET {{base}}/api/products/?city=Luanda

### Product detail (increments views)
GET {{base}}/api/products/<id>/

### Compare products
GET {{base}}/api/products/compare/?id=1&id=2

### Product Q&A
GET {{base}}/api/products/<id>/qa/
POST {{base}}/api/products/<id>/qa/
```json
{ "question": "Does this come with warranty?" }
```

### Duplicate a product (seller)
POST {{base}}/api/products/<id>/duplicate/

### Categories
GET {{base}}/api/products/categories/

---

## 4. CART

### Add to cart
POST {{base}}/api/cart/add/
```json
{ "product_id": 1, "quantity": 2 }
```

### View cart
GET {{base}}/api/cart/

### Update item quantity
PATCH {{base}}/api/cart/item/<id>/
```json
{ "quantity": 3 }
```

### Remove item
DELETE {{base}}/api/cart/item/<id>/

### Clear cart
DELETE {{base}}/api/cart/clear/

---

## 5. ORDERS

### Checkout (creates order)
POST {{base}}/api/orders/checkout/
```json
{
  "address_id": 1,
  "payment_method": "card",
  "notes": "Leave at door"
}
```

### My orders (buyer)
GET {{base}}/api/orders/my/

### Order detail
GET {{base}}/api/orders/<id>/

### Cancel order
POST {{base}}/api/orders/<id>/cancel/

### Mark delivered (buyer confirms receipt)
POST {{base}}/api/orders/<id>/confirm-delivery/

### Seller orders
GET {{base}}/api/orders/seller/

### Update order status (seller)
PATCH {{base}}/api/orders/<id>/status/
```json
{ "status": "shipped", "tracking_number": "DHL123456" }
```

---

## 6. PAYMENTS

### Wallet balance
GET {{base}}/api/payments/wallet/

### Wallet transactions
GET {{base}}/api/payments/wallet/transactions/

### Add bank account
POST {{base}}/api/payments/bank-accounts/
```json
{
  "bank_name": "BAI",
  "account_name": "João Silva",
  "account_number": "000123456789",
  "is_default": true
}
```

### Request payout
POST {{base}}/api/payments/payout/request/
```json
{ "amount": "5000", "bank_account_id": 1 }
```

### Payment webhook (simulated)
POST {{base}}/api/payments/webhook/
```json
{
  "event": "payment.success",
  "order_id": "1",
  "reference": "TXN_ABC123"
}
```

---

## 7. RECOMMENDATIONS

### Homepage feed (public)
GET {{base}}/api/recommendations/homepage/
Expected: 200 with sections array

### Personalised feed (auth)
GET {{base}}/api/recommendations/feed/
Expected: 200 — shows is_personalised: true/false

### Because you viewed
GET {{base}}/api/recommendations/because-you-viewed/

### Frequently bought together
GET {{base}}/api/recommendations/frequently-bought/<product_id>/

### Track interaction
POST {{base}}/api/recommendations/track/
```json
{ "product_id": 1, "type": "view" }
```
Valid types: view, wishlist, cart, purchase, share

### Set price alert
POST {{base}}/api/recommendations/price-alerts/
```json
{ "product_id": 1, "target_price": "40000" }
```

### Back in stock alert
POST {{base}}/api/recommendations/back-in-stock/
```json
{ "product_id": 2 }
```

### Live viewer count
GET {{base}}/api/recommendations/viewing/<product_id>/

### User interest profile
GET {{base}}/api/recommendations/interests/

---

## 8. COLLECTIONS

### All collections
GET {{base}}/api/collections/

### Collection detail
GET {{base}}/api/collections/<slug>/

### Product of the day
GET {{base}}/api/collections/product-of-day/

### Price history chart
GET {{base}}/api/collections/price-history/<product_id>/

### Platform announcements
GET {{base}}/api/collections/announcements/

### Seller spotlight
GET {{base}}/api/collections/seller-spotlight/

---

## 9. REVIEWS

### Seller reviews
GET {{base}}/api/reviews/seller/<seller_id>/

### Seller rating
GET {{base}}/api/reviews/seller/<seller_id>/rating/

### Leave review (must have purchased from seller)
POST {{base}}/api/reviews/create/
```json
{
  "seller": 2,
  "rating": 5,
  "comment": "Fast delivery, great product!"
}
```

### Product reviews
GET {{base}}/api/reviews/product/<product_id>/

### Mark review as helpful
POST {{base}}/api/reviews/<review_id>/helpful/

---

## 10. CHAT

### List conversations
GET {{base}}/api/chat/conversations/

### Start conversation with seller
POST {{base}}/api/chat/conversations/
```json
{ "seller_id": 2 }
```

### Get messages in conversation
GET {{base}}/api/chat/conversations/<id>/messages/

### Send message
POST {{base}}/api/chat/conversations/<id>/messages/
```json
{
  "content": "Hi, is this still available?",
  "shared_product_id": 1
}
```

### Mark messages as read
POST {{base}}/api/chat/conversations/<id>/read/

### Archive conversation
POST {{base}}/api/chat/conversations/<id>/archive/

### Quick reply templates (seller)
GET {{base}}/api/chat/quick-replies/
POST {{base}}/api/chat/quick-replies/
```json
{ "shortcut": "/yes", "message": "Yes, this is available! How many do you need?" }
```

### WebSocket (test with Postman WS or wscat)
wscat -c ws://127.0.0.1:8000/ws/chat/<conversation_id>/
Send: {"type": "message", "content": "Hello!"}
Send: {"type": "typing", "is_typing": true}
Send: {"type": "read"}

---

## 11. SEARCH

### Search
GET {{base}}/api/search/?q=iPhone

### Suggestions (autocomplete)
GET {{base}}/api/search/suggestions/?q=iPh

### Trending
GET {{base}}/api/search/trending/

### Recently viewed
GET {{base}}/api/search/recently-viewed/

### Search history
GET {{base}}/api/search/history/

---

## 12. TRUST & DISPUTES

### Open dispute
POST {{base}}/api/trust/disputes/
```json
{
  "order": 1,
  "type": "not_received",
  "description": "Order never arrived after 2 weeks"
}
```

### My disputes
GET {{base}}/api/trust/disputes/my/

---

## 13. WISHLIST

### Add to wishlist
POST {{base}}/api/wishlist/add/
```json
{ "product_id": 1 }
```

### View wishlist
GET {{base}}/api/wishlist/

### Move to cart
POST {{base}}/api/wishlist/move-to-cart/
```json
{ "product_id": 1 }
```

### Remove from wishlist
DELETE {{base}}/api/wishlist/<id>/

---

## 14. NOTIFICATIONS

### All notifications
GET {{base}}/api/notifications/

### Unread count
GET {{base}}/api/notifications/unread-count/

### Mark all read
PATCH {{base}}/api/notifications/mark-all-read/

### Mark one read
PATCH {{base}}/api/notifications/<id>/read/

---

## 15. SHIPPING

### Add address
POST {{base}}/api/shipping/addresses/
```json
{
  "label": "Home",
  "full_name": "João Silva",
  "phone": "+244923456789",
  "address_line": "Rua das Flores, 123",
  "city": "Luanda",
  "province": "Luanda",
  "country": "Angola"
}
```

### My addresses
GET {{base}}/api/shipping/addresses/

### Delivery zones
GET {{base}}/api/shipping/zones/

### Shipping estimate
GET {{base}}/api/shipping/estimate/?city=Luanda

---

## 16. i18n

### Currencies
GET {{base}}/api/i18n/currencies/

### Languages
GET {{base}}/api/i18n/languages/

### Price conversion
GET {{base}}/api/i18n/convert/?amount=1000&from=AOA&to=USD

---

## 17. SEO & HEALTH

### Health check
GET {{base}}/health/
Expected: {"status": "ok", "database": "ok"}

### robots.txt
GET {{base}}/robots.txt

### sitemap.xml
GET {{base}}/sitemap.xml

### Product JSON-LD schema
GET {{base}}/api/seo/schema/product/<id>/

---

## 18. ANALYTICS

### Seller performance
GET {{base}}/api/analytics/seller/performance/

### Admin real-time dashboard
GET {{base}}/api/analytics/admin/realtime/
Header: Authorization: Bearer {{admin_token}}

### Funnel analytics
GET {{base}}/api/analytics/funnel/?days=30

### Track funnel event
POST {{base}}/api/analytics/track/
```json
{ "event": "view", "product_id": 1 }
```

---

## 19. PROMOTIONS

### Active coupons / flash sales
GET {{base}}/api/promotions/flash-sales/

### Apply coupon at checkout
POST {{base}}/api/cart/apply-coupon/
```json
{ "code": "SAVE20" }
```

---

## 20. ADMIN ACTIONS

### Platform analytics
GET {{base}}/api/admin-actions/analytics/
Header: Authorization: Bearer {{admin_token}}

### User list
GET {{base}}/api/admin-actions/users/

### Suspend user
POST {{base}}/api/admin-actions/users/<id>/suspend/

### Approve payout
PATCH {{base}}/api/payments/payout/admin/<id>/
```json
{ "action": "approved", "note": "Verified and approved" }
```

---

## Common HTTP status codes you will see

| Code | Meaning |
|------|---------|
| 200 | OK |
| 201 | Created |
| 400 | Bad request (check body) |
| 401 | Not authenticated — add Bearer token |
| 403 | Forbidden — wrong role |
| 404 | Not found |
| 429 | Rate limited — slow down |
| 503 | Service degraded — check /health/ |
