# Two-step password reset with a change notification

- **Feature branch:** `feature/forgot-password-two-step-reset`
- **Repository:** `Plan-B-SAAS-Instance`
- **Base:** `main` at `f51fe96` (`Notifications change`)
- **Module version:** `19.0.1.1.0` (`planb_password_reset`)
- **Status:** implementation and acceptance validation complete; remote publication pending explicit approval.

---

## 1. Overview and business problem

The original forgot-password flow asked for the e-mail address, the one-time code and the
new password on a **single page**. A wrong code and a weak password were indistinguishable
to the controller, and a crafted POST could carry a password without proving that a code
had been accepted.

The requested behaviour was:

1. enter the address;
2. enter the code from the e-mail on its own page;
3. only after the code is accepted, open the page that sets the new password;
4. send the customer a “your password was changed” notice.

This branch delivers that flow as a reusable Odoo module that can be installed on the
management database and on every tenant database. Each database resets only its own users.

## 2. Scope and expected behaviour

### 2.1 Flow

```
GET  /web/forgot-password          page 1  e-mail address
POST /web/forgot-password          ──► page 2 (code only) + OTP e-mail
POST /web/forgot-password/verify   ──► page 3 (new password) + verify_token
POST /web/forgot-password/reset    ──► page 4 “Password changed” + notice e-mail
```

| Page | Asks for | Fields | Secrets carried |
|---|---|---|---|
| 1 | account address | `email` | CSRF |
| 2 | 6-digit code | `code` | CSRF + `request_token` |
| 3 | new password | `new_password`, `confirm_password` | CSRF + `request_token` + `verify_token` |
| 4 | nothing | — | CSRF |

The password endpoint refuses any request whose row is not `verified`. The `verify_token`
is 256 bits from `secrets.token_urlsafe(32)`, created only when a code is accepted, stored
on the request row, and sent only as a hidden form field — never in a URL. It is bound to
the browser session through `sha256('planb-reset:' + sid)` and is single-use.

### 2.2 Security properties

* A code moves `pending → verified` only on a correct, unexpired code, then `→ used` when
  the password is written. A consumed code or token cannot be replayed.
* A verified token is valid for `planb.reset.verify_window_minutes` (default `10`) and for
  at most `planb.reset.max_password_attempts` (default `5`) password submissions.
* The token is matched by request token **and** database UUID; a token minted in a tenant
  cannot be used on the management server, or vice versa.
* All three POST routes use CSRF protection and return 400 without a valid token.
* The flow has rate limits per address, IP and database; wrong codes burn the request after
  the configured limit.
* The stored code is a salted SHA-256 digest; the clear code is never stored or logged.
  `planb.reset.debug` is false by default.
* The completed change sends a notice to the account's own address with the login, UTC
  time, source IP and User-Agent. It contains no code, token or password. The login and
  User-Agent are escaped.
* Changing the password invalidates sessions opened before the change because Odoo's
  session token is derived from the password hash.
* Refusals on the password endpoint are deliberately generic and byte-identical for
  unknown request, wrong token, wrong browser, expired window or already-used token.

### 2.3 Non-goals

* No SMS channel; delivery is e-mail through Odoo's `mail` module.
* No reset link is sent; the flow is an OTP typed into the page.
* The module does not create or configure an outgoing mail server. A tenant without one
  will queue but not deliver the code; this is an environment prerequisite.

## 3. Architecture and implementation

### 3.1 Models

`models/password_reset.py` defines `planb.password.reset`, the request state machine and
its security-sensitive fields:

| Field | Purpose |
|---|---|
| `email` | Address typed by the visitor; the account is resolved exactly, not with SQL wildcards. |
| `code_hash` | Salted SHA-256 digest of the 6-digit code. |
| `state` | `pending`, `verified`, `used`, `expired`, `cancelled`, `failed`. |
| `request_token` | Opaque token for the code page. |
| `verify_token` | Single-use secret created when the code is accepted. |
| `session_hash` | SHA-256 of the browser session, domain-separated. |
| `verified_at` / `verified_until` | Ten-minute (configurable) password-page window. |
| `password_attempts` | Submissions on the verified page, capped. |
| `mail_id` / `notify_mail_id` | Audit links to the OTP and change-notice mail rows. |
| `expires_at`, `ip_address`, `user_agent` | Expiry and audit context. |

`models/res_users.py` adds the admin-side views/actions needed to inspect requests without
exposing secrets.

### 3.2 Controllers and templates

`controllers/main.py` implements the four routes and the helpers:

* `_session_sid()`, `_user_agent()`, `_session_fingerprint()`;
* `_render()` adds `Cache-Control: no-store`, `Referrer-Policy: no-referrer` and
  `X-Content-Type-Options: nosniff`;
* `_send_changed_notice()` creates the notice inside the request and sends it after commit
  on the same daemon-thread helper as the OTP; a purged row is logged at debug level, not
  as a traceback;
* the async mail sender tolerates a request row deleted while SMTP is in flight.

`views/forgot_password_templates.xml` contains page 1 (address), page 2 (code only), page 3
(new password with two hidden tokens) and page 4 (success). The templates use the website
layout and the platform's Arabic/English copy where applicable.

### 3.3 Data

`data/config_parameters.xml` adds:

| Key | Default | Meaning |
|---|---|---|
| `planb.reset.verify_window_minutes` | `10` | How long page 3 remains usable after code acceptance. |
| `planb.reset.max_password_attempts` | `5` | Password submissions per verified request. |

Existing rate-limit parameters remain in force. All values are non-secret and can be
changed in *Settings → Technical → System Parameters*.

## 4. Repository responsibilities and cross-repository relationships

| Repository | Responsibility | Relationship |
|---|---|---|
| `Plan-B-SAAS-Instance` | This feature: the complete `planb_password_reset` addon. | Installed independently on the management database and each tenant database. |
| `PLan-B-SAAS` | Management addons (`subscription_sale`, `planb_website`, …). | Not modified; the reset module is UI-independent of the SaaS addons. |
| `odoo19` | Odoo 19 runtime, `mail`, `base`. | No core change. |
| Environment root (`D:/WORK/Plan-B-SAAS-19`) | `test/forgot_password_suite.py`, `test/run.sh`, `changes/` documentation. | Acceptance suite and operational notes; not part of this module repository. |

The same module version is installed on both sides; each database owns its own request
rows and resets only its own users. The cross-database tests prove that a token from one
database cannot be used in the other.

## 5. Files changed

All paths are relative to `Plan-B-SAAS-Instance`.

| File | Change |
|---|---|
| `planb_password_reset/__init__.py` | Module import. |
| `planb_password_reset/__manifest__.py` | Installable Odoo 19 module, version `19.0.1.1.0`; depends on `base`, `mail`; loads security, data and views. |
| `planb_password_reset/controllers/__init__.py` | Controller import. |
| `planb_password_reset/controllers/main.py` | Four routes, session/token binding, generic refusals, async OTP/notice delivery, secure response headers. |
| `planb_password_reset/data/config_parameters.xml` | Verify window and password-attempt parameters. |
| `planb_password_reset/models/__init__.py` | Model imports. |
| `planb_password_reset/models/password_reset.py` | Request model, state machine, hashing, rate limiting, verification and notice body. |
| `planb_password_reset/models/res_users.py` | Admin-side request views/actions. |
| `planb_password_reset/security/ir.model.access.csv` | Access rules for the request model. |
| `planb_password_reset/views/forgot_password_templates.xml` | Pages 1–4. |
| `planb_password_reset/views/res_users_views.xml` | Admin views for reset requests. |

The untracked repository-root `.gitignore` present in the working environment was **not**
included: it is general Python hygiene, not part of the feature. Generated
`__pycache__`/`*.pyc` files are excluded from this branch.

## 6. Prerequisites and dependencies

* Odoo 19.0 with `base` and `mail` installed in the target database.
* The module installed on the management database and/or each tenant database that should
  offer self-service reset.
* A working outgoing mail server (`ir.mail_server`) in each database. The OTP is only
  useful if the address can receive it.
* A trusted `web.base.url` for each deployment so the e-mail points at the right origin.
* No extra Python package is required; the module uses the Odoo API and standard library.

No SMTP credentials, tokens or passwords are stored in this branch.

## 7. Configuration and deployment

### 7.1 Install/upgrade on a database

```bash
~/planb-saas/venv/bin/python odoo19/odoo-bin \
  -c conf/odoo-management.conf -d <database> \
  -u planb_password_reset --stop-after-init --no-http
```

Use `conf/odoo-tenant.conf` for a tenant database. The module is independent per database;
install/upgrade every database that should expose the flow.

### 7.2 Restart

```bash
bash setup/stop_all.sh
bash setup/start_all.sh
```

### 7.3 Verify

1. Open `http://<host>:<port>/web/forgot-password` (add `?db=<tenant>` when using the
   tenant port).
2. Request a code for a test account; confirm the message says a code was sent, and that
   page 2 has **only** the code field.
3. Enter the code; page 3 must show the new-password fields and a hidden `verify_token`.
4. Set a valid password; page 4 must confirm the change and the account must receive the
   “Your Plan B password was changed” notice.
5. Confirm the notice contains the time, source IP and User-Agent and no OTP/token/password.

### 7.4 Deployment order

1. Back up each database.
2. Confirm an outgoing mail server is configured and the envelope sender is authorised.
3. Upgrade the module on the management database and each tenant database.
4. Restart the servers.
5. Run the acceptance suite (or a manual walk-through) against one management and one
   tenant database.

## 8. Tests and validation

### 8.1 Executed for this release (2026-10-22)

| Check | Command | Result |
|---|---|---|
| Acceptance suite | `python test/forgot_password_suite.py` | **PASS — 19 passed, 0 failed, 19 total** |
| Python syntax | `python3 -m py_compile` on 7 module `.py` files | **PASS** |
| XML well-formedness | `xml.etree.ElementTree.parse` on 3 module `.xml` files | **PASS** |
| Test transcript | `test/results/forgot-password-release-20261022.log` | recorded |

The suite drives the real HTTP endpoints of the management server (`:8020`, database
`subscribeOne`) and the tenant server (`:8030`, database `tenant_test_reset_999`), real
PostgreSQL queries and real SMTP delivery. It resets its disposable accounts before the
run and restores the review account's requested password at the end; the transcript
confirms both.

Covered tests: T01–T14 and T16–T20, including byte-identical enumeration responses,
two-step flow, old-password invalidation, replay, expiry, cross-database rejection, rate
limiting, log secrecy, privilege preservation, correct origin, CSRF, password policy,
hashed storage, wildcard handling, token skipping/browser binding, change notice, request
supersession and session invalidation. T15 (`setup/verify.sh`) is the separate platform
check and was **not** rerun in this release; the historical result is **26 passed, 0 failed,
1 warning**.

### 8.2 What is not covered

* Browser-specific rendering, accessibility and Arabic/English copy review are manual.
* SMTP deliverability depends on the configured server; the suite proves the mail row was
  accepted by SMTP, not that a third-party inbox placed it in the inbox.
* Load/rate-limit behaviour under a distributed attack is not simulated; the per-database
  counters are tested sequentially.
* A production tenant created before this module was installed needs an explicit module
  upgrade.

## 9. Database migration and compatibility

The module is additive:

* new table(s) for reset requests and new columns on existing request rows;
* new `ir.config_parameter` rows;
* new access rules and views.

No existing table is dropped and no product data is rewritten. The module version is
`19.0.1.1.0`. If the code is reverted, the added columns/parameters are harmless; drop them
only if the module is also removed:

```sql
alter table planb_password_reset
    drop column verify_token, drop column session_hash,
    drop column verified_at, drop column verified_until,
    drop column password_attempts, drop column notify_mail_id;
delete from ir_config_parameter
    where key in ('planb.reset.verify_window_minutes',
                  'planb.reset.max_password_attempts');
```

## 10. Deployment compatibility and integration order

* The module is UI-independent of the management SaaS addons; install it after
  `base`/`mail` and before exposing the forgot-password link.
* The tenant and management servers can run different module versions temporarily during
  a rolling upgrade, but a token minted on one database is never valid on the other.
* If a tenant is provisioned from a template that predates this module, run `-u
  planb_password_reset` (or install it) before enabling the flow there.

## 11. Rollback

1. Restore the previous module files (this branch is the reference for the new version).
2. Run `-u planb_password_reset` on every database that was upgraded.
3. Restart the servers.
4. Optionally drop the additive columns/parameters using the SQL above.

The previous one-page flow returns after the code rollback. Passwords already changed
through the new flow remain changed; rollback does not restore old passwords.

## 12. Known limitations

* A reload of page 3 replays the POST; the row is no longer `pending`, so the visitor must
  start again. This is the deliberate cost of not putting the token in a URL.
* The e-mail notice is a notification channel, not a recovery channel. It never contains a
  credential.
* A database without a working outgoing mail server will not deliver the code. The page
  cannot detect this reliably before queueing.
* The admin views expose request metadata, not the OTP or token; protect the admin group
  accordingly.
* The acceptance suite requires the live servers, PostgreSQL and SMTP; it is not a
  self-contained unit test.

## 13. Branch, commits and publication

* Branch: `feature/forgot-password-two-step-reset`
* Base: `main` @ `f51fe96`
* Local commit: recorded in `release/reports/publication-status.md` after the branch is
  committed.
* Remote: `https://github.com/business-sense-corp/Plan-B-SAAS-Instance.git`
* Push: **not performed**. Explicit approval is required. No pull request exists yet.

## 14. Evidence and related documents

* `changes/fixed_errors/05-two-step-reset-and-change-notice.md` — design, threat model,
  evidence and rollback.
* `changes/10-forgot-password/` — original module design and integration notes.
* `test/forgot_password_suite.py`, `test/run.sh`, `test/README.md`.
* `test/results/forgot-password-release-20261022.log` — this release's transcript.
