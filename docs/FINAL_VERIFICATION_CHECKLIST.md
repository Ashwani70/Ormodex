# Final Verification Checklist

Run through this on `https://erp.mycompany.com` after every production
deploy (at minimum after the very first one, and after any change touching
auth, PDF generation, or file storage). Each item notes what would actually
indicate a real problem, not just "does it look okay."

## ✓ Login
- [ ] Log in with a real (non-admin-bootstrap) account.
- [ ] Confirm the session survives a page refresh (cookie-based auth
  working — a failure here often means `ENV=production` or `SameSite`
  cookie config is wrong; see `docs/SECURITY_CHECKLIST.md`).
- [ ] Log out, confirm you're actually redirected to `/login` and a
  protected route redirects you back if visited directly.
- [ ] If MFA is enabled on the test account, confirm the challenge step works.

## ✓ Dashboard
- [ ] Dashboard loads without a console error and without any request
  failing in the Network tab.
- [ ] KPI cards show real numbers (not all zeros — zeros everywhere usually
  means the API calls are failing silently, not that the business genuinely
  has no data).

## ✓ CRUD operations
- [ ] Create one record in at least one module (e.g. a Product or a
  Purchase Order) — confirm it saves and appears in its list view.
- [ ] Edit that record, confirm the change persists after a page refresh.
- [ ] Delete it (or cancel/void, per that module's actual delete semantics —
  several modules intentionally block hard-delete after certain states;
  that's correct behavior, not a bug).

## ✓ Reports
- [ ] Open at least one report page (e.g. MIS Reports, Stock Log) and
  confirm it renders with real data, not an empty/error state.

## ✓ PDF generation
- [ ] Generate a PDF for at least one document type (Invoice, Purchase
  Order, or similar) — confirm it downloads/opens and actually contains the
  expected line items, HSN codes, and totals (not a blank or malformed PDF —
  this codebase has had real historical bugs here around silently-dropped
  fields; see project memory on the PDF/items-lines-column fixes).

## ✓ File upload/download
- [ ] Upload a product image or company logo.
- [ ] **Redeploy the backend service, then confirm the uploaded file is
  still there.** This specifically verifies the Railway Volume is correctly
  mounted (see `docs/PRODUCTION_DEPLOYMENT_GUIDE.md §2`) — skipping this
  check means you won't find out the Volume is misconfigured until a real
  user's uploaded file silently disappears.

## ✓ Printing
- [ ] Trigger a print action (native browser print or an in-app print
  button) and confirm the print preview shows correctly formatted content.

## ✓ Notifications
- [ ] Trigger an in-app toast notification (e.g. after a successful save).
- [ ] If running the desktop build, confirm a native OS notification fires
  where expected (see the desktop-app session's notification work).

## ✓ Email
- [ ] Trigger a real email send (e.g. share a document, password reset) and
  confirm it actually arrives — check the Resend dashboard
  (`RESEND_API_KEY`'s account) for delivery status if it doesn't land in the
  inbox, since a silent send failure is easy to miss from the app side alone.

## ✓ Role permissions
- [ ] Log in as a non-admin role and confirm at least one admin-only page/
  action is correctly blocked (e.g. `/api/diagnostics`, user management).
- [ ] Confirm a role WITH access to a module can actually use it — testing
  only the "blocked" side risks missing an over-restrictive permission bug.

## ✓ Mobile responsiveness
- [ ] Open the app on an actual phone (or DevTools device emulation at
  minimum) and confirm the layout doesn't break — this app targets desktop-
  first ERP workflows, so "responsive" here means "usable for read/approve
  workflows on a phone," not a full mobile-optimized redesign of every dense
  data-table screen.
- [ ] If the PWA is installed, confirm it opens in standalone mode (no
  browser chrome) and the offline banner appears correctly when connectivity
  is dropped.

## Sign-off

Record the date, who ran this checklist, and the deployed commit SHA
somewhere durable (a pinned issue, a deployment log channel) — "we verified
it" is only useful if you can later answer "verified against which version."
