# MICHA — Security Review Checklist

Every pull request touching authentication, payments, orders, or user data
must be reviewed against this checklist before merging.

---

## Authentication & Access Control

- [ ] Does every view that accesses user data filter by `request.user`?
- [ ] Does every serialiser use an explicit `fields` list (never `__all__`)?
- [ ] Are all write fields explicitly listed in `read_only_fields`?
- [ ] Does the view use `get_object_or_404(Model, pk=pk, user=request.user)` not just `pk=pk`?
- [ ] Are financial endpoints (`/payout/`, `/bank-accounts/`, `/refund/`) protected by `Requires2FAForFinancial`?
- [ ] Are admin endpoints protected by `IsAdminOrSuperuser` AND `AdminIPAllowlistMiddleware`?
- [ ] Is `IsNotSuspended` applied to all buyer and seller actions?
- [ ] Does linking a social provider require password confirmation?

## Cryptography & Data Storage

- [ ] Are any OTPs, tokens, or secrets stored in plain text? (Must use `_hash_otp()` or `_hash_token()`)
- [ ] Are any bank accounts or national IDs stored without `EncryptedCharField`?
- [ ] Does `set_password()` revoke existing JWT tokens?
- [ ] Are new model fields containing PII marked appropriately in the data classification doc?

## Input Validation

- [ ] Is all user text input sanitised before storage? (bleach middleware handles JSON, but validate in serialisers too)
- [ ] Are file uploads validated for MIME type using `validate_image()` or `validate_document()`?
- [ ] Are search query inputs validated and length-limited?
- [ ] Are numeric inputs (amounts, quantities, page numbers) validated to be positive?
- [ ] Are URL parameters validated to be the correct type (UUID, integer)?

## Output & Information Disclosure

- [ ] Do error messages reveal internal implementation details? (must use generic messages in production)
- [ ] Do 404 responses reveal whether a resource exists? (use same response for not-found vs unauthorised)
- [ ] Are stack traces disabled in production? (`DEBUG=False`)
- [ ] Do API responses include any fields the user should not see? (other users' emails, internal IDs)

## Logging & Audit

- [ ] Are security events (auth failures, privilege changes, large transactions) logged via `log_security_event()`?
- [ ] Are admin actions logged via `AdminActionLog.log()`?
- [ ] Do log messages contain PII? (emails, national IDs, bank accounts must not appear in logs)
- [ ] Is the new endpoint covered by the rate limiter?

## Payment & Financial

- [ ] Does checkout use `@transaction.atomic`?
- [ ] Does the webhook verify HMAC signature before processing?
- [ ] Do wallet operations use `select_for_update()`?
- [ ] Is the order total verified before payment is processed?
- [ ] Do payout requests check for existing pending payouts?

## Compliance (Lei 22/11 / GDPR)

- [ ] If new PII is collected, is it documented in the data processing register?
- [ ] If new PII is collected, is it included in the data export endpoint?
- [ ] If new PII is collected, is it included in the account deletion/anonymisation task?
- [ ] Is consent required for any new marketing or tracking feature?

---

## Reviewer sign-off

Before approving any PR that touches auth, payments, or PII:

1. Run `bandit -r apps/ -ll` and confirm no high-severity issues
2. Run `pip-audit` and confirm no new vulnerable dependencies
3. Check that no secrets appear in the diff (`detect-secrets scan`)
4. Verify the endpoint is in the Postman test collection
