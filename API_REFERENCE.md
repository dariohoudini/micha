# MICHA API Reference

Base URL: `http://localhost:8000/api`
Auth header: `Authorization: Bearer <access_token>`

---

## Auth `/api/auth/`
| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| POST | `/auth/register/` | No | Register new user |
| POST | `/auth/login/` | No | Login, returns JWT tokens |
| POST | `/auth/logout/` | Yes | Blacklist refresh token |
| POST | `/auth/token/refresh/` | No | Refresh access token |
| GET/PUT | `/auth/profile/` | Yes | View or update own profile |
| POST | `/auth/change-password/` | Yes | Change own password |
| GET | `/auth/users/<id>/` | No | Public user profile |

## Verification `/api/verification/`
| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| POST | `/verification/apply/` | Yes | Submit verification docs |
| GET | `/verification/status/` | Yes | Own verification status |
| POST | `/verification/selfie/` | Yes | Upload monthly selfie |
| GET | `/verification/admin/` | Admin | List all verifications |
| POST | `/verification/admin/<id>/action/` | Admin | Approve/reject/suspend |

## Stores `/api/stores/`
| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| GET | `/stores/` | No | List all active stores |
| GET | `/stores/my/` | Yes | Your own stores |
| GET | `/stores/<id>/` | No | Store detail + products |
| POST | `/stores/<id>/review/` | Yes | Review a store |
| GET | `/stores/<id>/reviews/` | No | All reviews for a store |

## Products `/api/products/`
| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| GET | `/products/` | No | Browse all products |
| GET | `/products/<id>/` | No | Product detail (increments views) |
| GET | `/products/categories/` | No | All categories |

Filters: `?category=` `?min_price=` `?max_price=` `?city=` `?sale_type=sale|rent` `?search=` `?ordering=price|-price`

## Seller `/api/seller/`
| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| GET | `/seller/dashboard/` | Seller | Stats overview |
| GET | `/seller/verify/` | Seller | Own verification status |
| POST | `/seller/store/create/` | Seller | Create store |
| GET/PUT | `/seller/store/<id>/` | Seller | Update own store |
| GET | `/seller/stores/` | Seller | List own stores |
| POST | `/seller/product/create/` | Seller | Create product |
| GET/PUT/DELETE | `/seller/product/<id>/` | Seller | Manage product |
| GET | `/seller/products/` | Seller | List own products |

## Chat `/api/chat/`
| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| GET | `/chat/conversations/` | Yes | Your conversations |
| POST | `/chat/conversations/` | Yes | Start chat `{"seller_id": id}` |
| GET | `/chat/conversations/<id>/messages/` | Yes | Get messages |
| POST | `/chat/conversations/<id>/messages/` | Yes | Send message |
| POST | `/chat/conversations/<id>/read/` | Yes | Mark messages read |

## Reviews `/api/reviews/`
| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| POST | `/reviews/create/` | Yes | Review a seller |
| GET | `/reviews/seller/<id>/` | No | All reviews for a seller |
| GET | `/reviews/seller/<id>/rating/` | No | Avg rating for a seller |
| GET/PUT/DELETE | `/reviews/<id>/` | Yes | Edit or delete own review |

## Reports `/api/reports/`
| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| POST | `/reports/create/` | Yes | Report a seller or product |
| GET | `/reports/admin/` | Admin | All reports |
| PATCH | `/reports/admin/<id>/` | Admin | Update report status |

## Admin Actions `/api/admin-actions/`
| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| GET | `/admin-actions/analytics/` | Admin | Platform metrics |
| GET | `/admin-actions/users/` | Admin | List all users |
| POST | `/admin-actions/user/` | Admin | Warn/suspend/ban a user |
| GET | `/admin-actions/user/history/` | Admin | Action history log |
| POST | `/admin-actions/product/<id>/moderate/` | Admin | Hide/restore/remove product |
| GET | `/admin-actions/product/moderation-log/` | Admin | Product mod history |

## Listings `/api/listings/`
| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| GET | `/listings/` | No | Browse all listings |
| POST | `/listings/create/` | Yes | Create listing |
| GET | `/listings/my/` | Yes | Your own listings |
| GET | `/listings/<uuid>/` | No | Listing detail |
| GET/PUT/DELETE | `/listings/<uuid>/edit/` | Yes | Edit or delete own listing |

## Accounts `/api/accounts/`
| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| POST | `/accounts/block/` | Yes | Block a user |
| DELETE | `/accounts/unblock/<id>/` | Yes | Unblock a user |
| GET | `/accounts/blocked/` | Yes | List blocked users |
