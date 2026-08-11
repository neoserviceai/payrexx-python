# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres
to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.0] — 2026-08-03

Coverage extended using the official [PHP SDK](https://github.com/payrexx/payrexx-php)
as the reference, which documents more of the API than the REST reference does.
Four resources became fourteen.

### Added

- Resources: `subscription`, `invoice`, `page`, `bill` (Swiss QR bill — positions,
  reminders, attachments, cash discounts), `payout`, `qr_code`, `design`,
  `payment_method`, `signature_check`, `auth_token`
- `transaction`: `charge`, `pre_authorize`, `send_receipt`, `cancel`, and the
  server-side list filters (`filterDatetimeUtc*`, `filterMyTransactionsOnly`,
  `orderByTime`)
- `gateway.create`: all 35 request fields, including `basket`, `validity`,
  `skip_result_page`, `look_and_feel_profile`, `qr_code_session_id` and the
  subscription parameters
- `ecr`: `purpose`, `discount`, and a `shop_item` builder
- `TerminalPairing` now exposes the configuration the terminal reports —
  `currency`, `language`, `point_of_sale_name`, `timezone`, `has_tipping`
- `Currency`, `Interval` and `SubscriptionStatus` enums
- Three transaction statuses that exist only in the PHP SDK: `initiated`,
  `insecure`, `uncaptured`
- `PUT` and `PATCH` support on the client
- CI on Python 3.10–3.13, pre-commit configuration, `SECURITY.md`,
  `CONTRIBUTING.md`

### Changed

- **API version pinned to v1.16** (was v1.0). v1.15 is where Payrexx introduced
  specific HTTP status codes for failed requests, so the error mapping cannot be
  relied on below it. v1.17 does not exist.
- **`ecr.cancel_payment` and `ecr.void_payment` now put the payment id in the
  path** — `/ecr/{sn}/payment/{id}/cancel`, as the PHP SDK builds it, not in the
  request body as the REST reference shows.
- `ecr.payment_methods` is sent as `GET`, per the SDK, not `POST`.
- Both now return a parsed `EcrPayment` instead of a raw payload.
- `PaymentMethodInfo` reworked: `id` is the identifier (`"mastercard"`), `name` is
  a human label, and `label` / `logo` are per-language maps. Adds `label_for`,
  `logo_for`, `currencies` and `payment_types`.
- `Gateway` exposes `app_link`, `transaction_id`, `application_fee`, `request_id`.
- `webhook` helpers accept `bytes | str` for the raw body.

### Fixed

- The webhook helpers declared `raw_body: bytes` while guarding for `str`, leaving
  the guard unreachable. Found by `mypy --warn-unreachable`; frameworks do hand
  over a decoded body, so the type was wrong rather than the guard.

## [0.1.0] — 2026-08-03

First release. Hosted gateways, transactions, payment providers, POS terminals
(ECR) and webhook verification, with the four silent-failure traps encoded:
mandatory `instance`, PHP indexed-bracket list encoding, no idempotency anywhere,
and the three sharp edges of webhook signature verification.
