# Auth Testing Playbook — Gravity ERP

Backend uses JWT-based custom auth (FastAPI + MongoDB). Cookies are httpOnly and `samesite=none; secure=true` (works because the preview ingress is HTTPS).

## Quick API Test
```
curl -c cookies.txt -X POST $REACT_APP_BACKEND_URL/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@gravityengineering.com","password":"Admin@123"}'

curl -b cookies.txt $REACT_APP_BACKEND_URL/api/auth/me
```

Login returns the user object, sets both `access_token` and `refresh_token` cookies, and also includes `access_token` in the JSON for clients that want to use a `Authorization: Bearer` header.

## Mongo Verification
```
db.users.find({role:"admin"}, {password_hash:0}).pretty()
db.users.getIndexes()  // confirm unique index on email
db.products.getIndexes()  // unique index on sku
```

## Role Checks
- Admin-only: DELETE on users / products / warehouses / suppliers / purchase-orders / customers / leads / quotations / sales-orders / invoices / dispatches.
- Employees can do GET/POST/PUT but not hard-delete.
