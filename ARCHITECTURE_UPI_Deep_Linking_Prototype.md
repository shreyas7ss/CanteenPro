# LineZero — Architecture & Implementation Spec

> **For Claude Code:** This document is the source of truth for building LineZero. Implement in the build order given. Do not invent extra dependencies. Stick to the stack decisions below. Where a value is unknown (API keys, salt keys), read it from environment variables — never hardcode.

---

## 1. What LineZero is

A canteen pre-order system for college campuses. Student scans a QR code → opens a Telegram bot → browses menu → orders → pays via UPI Deep Linking → gets a token number → canteen staff sees the **paid** order on a live dashboard → prepares it → marks ready → student picks up without queueing.

**Core design principle — payment-first order visibility:** an order only appears on the staff dashboard *after* successful payment. Unpaid/abandoned orders never reach the staff workflow.

---

## 2. Stack (decided — do not substitute)

| Layer | Choice | Notes |
| --- | --- | --- |
| Messaging | Telegram Bot API | via `python-telegram-bot` v20+ (async) |
| Payments | Raw UPI deep linking (`upi://pay`) | no PG, no SDK, no KYC — bot builds the link itself against the canteen's own UPI ID |
| Database | Supabase (Postgres) | REST API + Realtime + table editor |
| Backend | Python 3.11+ | bot polling + FastAPI (pay redirect + health check) in one service |
| Backend host | Fly.io | single machine, no spin-down |
| Dashboard | Static HTML | hosted on Netlify or Vercel |

**Language/runtime:** Python 3.11+, async throughout.

---

## 3. Component topology

```
Student (Telegram app)
   │
   ▼
┌─────────────────────────────────────────┐
│  Fly.io service (one Python process)     │
│                                          │
│  ├── Telegram bot (polling loop)         │
│  │     handles /start, menu, cart,       │
│  │     order creation, sends pay link,   │
│  │     handles "I've Paid" tap           │
│  │                                       │
│  └── FastAPI app                         │
│        GET /pay/{txn_id} ← 302 redirect to upi://pay │
│        GET /health       ← Fly health check │
└─────────────────────────────────────────┘
   │                              │
   │ REST + Realtime              │ https redirect → upi://pay?pa=...
   ▼                              ▼
┌──────────────┐        Student's UPI app
│  Supabase    │        (GPay/PhonePe/Paytm/…)
│  Postgres    │        opens directly, pays
│  + Realtime  │        canteen's own VPA
└──────────────┘        directly — no server in between
   ▲
   │ Realtime WS subscription
   │
┌──────────────────────────────┐
│  Static dashboard (Netlify)  │
│  staff queue + owner analytics│
└──────────────────────────────┘
```

The bot has no inbound server of its own — it polls `api.telegram.org`. FastAPI exists to (a) 302-redirect Telegram's inline button (which only accepts `http(s)` URLs) to the actual `upi://pay` deep link, and (b) give Fly.io a port to health-check so the machine stays alive.

**No gateway, no callback:** the deep link points straight at the canteen's own UPI ID — no PG sits in the middle, so nothing ever calls the backend to confirm payment happened. Confirmation is the student tapping **"I've Paid"** in the bot, handled directly as a Telegram callback query (not a webhook). This is a deliberate trust tradeoff, not an oversight — see §7 step 8 and §13.

---

## 4. Repository structure

```
linezero/
├── app/
│   ├── __init__.py
│   ├── main.py            # entrypoint: starts FastAPI + bot together
│   ├── bot.py             # Telegram handlers (menu, cart, order, pay link)
│   ├── server.py          # FastAPI router: GET /pay/{txn_id} redirect, GET /health
│   ├── upi.py             # builds upi://pay deep link + QR code image, no external calls
│   ├── db.py              # Supabase client wrapper (REST calls)
│   ├── cart.py            # in-memory cart state per telegram_user_id
│   └── config.py          # env var loading + validation
├── schema.sql             # run in Supabase SQL editor
├── dashboard.html         # static, deploy to Netlify
├── requirements.txt
├── Dockerfile
├── fly.toml
├── .env.example
└── README.md
```

---

## 5. How bot + FastAPI run in one process

`app/main.py` starts the FastAPI app with uvicorn and launches the bot's polling loop as a concurrent asyncio task. Because `python-telegram-bot` v20 is async, both share one event loop.

```python
# app/main.py — shape only, implement fully
import asyncio
import uvicorn
from app.server import app             # FastAPI instance (GET /pay/{txn_id}, GET /health)
from app.bot import build_application  # returns telegram Application

async def run_bot(application):
    await application.initialize()
    await application.start()
    await application.updater.start_polling()

async def main():
    application = build_application()
    config = uvicorn.Config(app, host="0.0.0.0", port=8080, loop="asyncio")
    server = uvicorn.Server(config)
    await asyncio.gather(run_bot(application), server.serve())

if __name__ == "__main__":
    asyncio.run(main())
```

No shared state needed between the two halves this time: `/pay/{txn_id}` is a stateless 302 redirect (all the fields it needs travel in the query string — see §8), and "I've Paid" is a Telegram callback query handled entirely inside `bot.py`, which already holds the `application` object. FastAPI never needs to reach into the bot.

---

## 6. Database schema

Three tables. Full DDL lives in `schema.sql`; this is the contract.

### `menu_items`
| column | type | notes |
| --- | --- | --- |
| id | uuid PK | default `gen_random_uuid()` |
| name | text | |
| price | numeric(10,2) | rupees |
| category | text | e.g. Snacks, Beverages |
| is_available | boolean | default true |
| image_url | text | nullable |
| created_at | timestamptz | default now() |

### `orders`
| column | type | notes |
| --- | --- | --- |
| id | uuid PK | default `gen_random_uuid()` |
| token_number | int | null until paid; assigned by `assign_next_token` |
| telegram_user_id | bigint | |
| telegram_username | text | nullable |
| student_name | text | nullable |
| roll_number | text | nullable |
| total_amount | numeric(10,2) | |
| merchant_transaction_id | text UNIQUE | our own ref, used as the `tr` param in the `upi://pay` link |
| student_utr | text | nullable — 12-digit UPI transaction ref, only populated if the optional UTR-capture hardening (§11) is turned on |
| payment_mode | text | nullable — which UPI app the student says they paid with, if asked |
| status | text | see lifecycle below |
| notes | text | nullable |
| placed_at | timestamptz | default now() |
| paid_at | timestamptz | stamped by `assign_next_token` |
| ready_at | timestamptz | stamped when staff marks ready |
| completed_at | timestamptz | stamped when staff marks done |

### `order_items`
| column | type | notes |
| --- | --- | --- |
| id | uuid PK | |
| order_id | uuid FK → orders.id | on delete cascade |
| menu_item_id | uuid FK → menu_items.id | |
| item_name | text | **snapshot** at order time |
| unit_price | numeric(10,2) | **snapshot** at order time |
| quantity | int | |

Item name and price are denormalized into `order_items` so later menu edits never rewrite order history.

### Status lifecycle
```
pending_payment ──► paid ──► ready ──► completed
       │
       └──► cancelled   (any time before paid)
```

### Helper function
`assign_next_token(p_order_id uuid) returns int` — runs atomically:
1. computes next per-day token (count of today's paid orders + 1)
2. sets `status = 'paid'`
3. stamps `paid_at = now()`
4. returns the token number

Called when the student taps **"I've Paid"** in the bot — there is no independent server-side verification (see §7 step 8, §13). Must still be transaction-safe so two simultaneous "I've Paid" taps never collide on a token.

### RLS (prototype posture)
- **anon key**: can `SELECT` everything and `UPDATE orders` (so dashboard mark-ready buttons work without auth)
- **service role key**: used by the Python backend, bypasses RLS
- Production hardening (locking down anon UPDATE, adding staff auth) is deferred — see §11.

---

## 7. End-to-end order flow

1. Student opens bot → bot pulls live menu (`is_available = true`) from Supabase
2. Student taps items via inline keyboard → cart held in memory keyed by `telegram_user_id`
3. Bot shows cart summary + total
4. Student taps **Confirm & Pay**:
   - bot generates `merchant_transaction_id = uuid4()`
   - inserts `orders` row (`status = 'pending_payment'`) + `order_items` rows
5. Bot calls `upi.build_pay_link(amount, merchant_transaction_id, note)` — pure local string building, no network call (see §8)
6. Bot sends the student **two ways to pay**, since Telegram inline "URL" buttons only accept `http(s)`:
   - an inline button pointing at `https://<fly-app>/pay/{merchant_transaction_id}?...`, which 302-redirects to the real `upi://pay?...` link (works great on mobile — one tap opens the UPI app picker)
   - a QR code image of the same `upi://pay?...` string (works on any device, including Telegram Desktop, by scanning with any UPI app)
7. Student pays directly to the canteen's own UPI ID — no server is involved in this step at all
8. Student taps **"I've Paid"** in the bot (a Telegram callback query, handled in `bot.py` — not a webhook):
   - (Prototype posture) no independent verification that the payment actually arrived
   - bot marks the order paid and calls `assign_next_token(order_id)` → status `paid`, token assigned
   - notify student via bot: "Paid ✅ Your token is #N"
   - staff can spot-check the canteen's own UPI app/bank statement periodically; see §11 for the optional UTR-capture upgrade if blind trust becomes a problem
9. Dashboard (subscribed to Supabase Realtime on `orders`) shows the new paid order live
10. Staff taps **Mark ready** → `status = 'ready'`, `ready_at` stamped → bot notifies student
11. Student collects → staff taps **Completed** → `status = 'completed'`, `completed_at` stamped

---

## 8. UPI deep link implementation

No PG, no SDK, no API call of any kind — the deep link is built entirely with a local string template against the canteen's own UPI ID. Three things matter: **the URI scheme**, **generating a scannable fallback**, and **the https→upi redirect trick Telegram forces on you**.

### The `upi://pay` URI scheme
Standard NPCI UPI linking parameters (query-string style, on a `upi://pay` scheme):

| param | meaning | example |
| --- | --- | --- |
| `pa` | payee VPA — the canteen's own UPI ID | `canteen@oksbi` |
| `pn` | payee display name shown in the paying app | `LineZero Canteen` |
| `am` | amount, **plain decimal rupees**, not paise | `45.00` |
| `tr` | our own unique transaction ref | `merchant_transaction_id` |
| `tn` | transaction note, URL-encoded | `LineZero order 8f3a` |
| `cu` | currency, always | `INR` |

> **Note for Claude Code:** confirm this field list against the current official NPCI UPI linking specification at build time — treat the table above as the structure to implement, not a guarantee every field/behavior is unchanged. Some UPI apps additionally accept `mc` (merchant category code); leave it out unless testing shows a target app needs it.

### Build the link (shape)
```python
# app/upi.py
from urllib.parse import urlencode

def build_pay_link(amount: float, merchant_txn_id: str, note: str) -> str:
    params = {
        "pa": UPI_VPA,
        "pn": UPI_PAYEE_NAME,
        "am": f"{amount:.2f}",
        "tr": merchant_txn_id,
        "tn": note,
        "cu": "INR",
    }
    return "upi://pay?" + urlencode(params)

def build_qr_png(upi_link: str) -> bytes:
    # qrcode.make(upi_link) → PNG bytes, sent as a Telegram photo alongside the button
    ...
```

No amount rounding surprises, no signature, no HTTP round-trip — this can fail closed only if `UPI_VPA` is misconfigured, which `config.py` should validate on startup. Add `qrcode` (with the `pil` extra) to `requirements.txt` — the only new dependency this whole approach introduces.

### The Telegram https→upi redirect
Telegram's inline keyboard "URL" button type only accepts `http(s)` URLs, not custom schemes like `upi://`. So the bot doesn't put the raw deep link on the button — it links to a small redirect route on our own FastAPI app, which 302s straight through:

```python
# app/server.py
from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from app.upi import build_pay_link

app = FastAPI()

@app.get("/pay/{txn_id}")
async def pay_redirect(txn_id: str, pa: str, pn: str, am: str, tn: str):
    link = build_pay_link(float(am), txn_id, tn)  # or rebuild directly from query params
    return RedirectResponse(link, status_code=302)

@app.get("/health")
async def health():
    return {"status": "ok"}
```

Every field the redirect needs travels in its own query string (set by the bot when it builds the button URL) — the route never touches Supabase or the bot, so it stays fully stateless.

### No KYC, nothing to sign up for
`pa` is just the canteen's own existing UPI ID — a personal GPay/PhonePe/Paytm handle or a current-account VPA from any bank works. There's no merchant account, no business registration, no PG dashboard to configure. The tradeoff for skipping all of that is zero automated payment verification (§7 step 8, §13) — if that becomes a real problem once volume picks up, the upgrade path is UTR capture (§11), not necessarily a PG.

---

## 9. Environment variables

Provide a `.env.example`. Never commit real values.

```
# Telegram
TELEGRAM_BOT_TOKEN=

# Supabase
SUPABASE_URL=
SUPABASE_SERVICE_ROLE_KEY=     # backend uses this (bypasses RLS)
SUPABASE_ANON_KEY=             # dashboard uses this (in dashboard.html)

# UPI Deep Linking
UPI_VPA=                        # canteen's own UPI ID, e.g. canteen@oksbi
UPI_PAYEE_NAME=                 # display name shown in the student's UPI app
UPI_REDIRECT_BASE_URL=https://<your-fly-app>.fly.dev   # used to build the /pay/{txn_id} button URL

# App
PORT=8080
```

`config.py` loads these and fails loud on startup if any required one is missing.

---

## 10. Deployment (Fly.io)

`Dockerfile` (slim Python base), `fly.toml` exposing port 8080 with an HTTP health check on `/health`.

```toml
# fly.toml — shape only
app = "linezero"
primary_region = "bom"          # Mumbai, closest to campus

[http_service]
  internal_port = 8080
  force_https = true
  auto_stop_machines = false    # IMPORTANT: keep bot polling alive
  min_machines_running = 1

[[http_service.checks]]
  path = "/health"
  interval = "30s"
```

`auto_stop_machines = false` and `min_machines_running = 1` are non-negotiable — the polling bot must never sleep.

Deploy:
```
fly launch        # first time, generates app
fly secrets set TELEGRAM_BOT_TOKEN=... SUPABASE_SERVICE_ROLE_KEY=... (etc.)
fly deploy
```

Dashboard deploys separately to Netlify (drag-drop `dashboard.html`, set Supabase URL + anon key inline).

---

## 11. Production hardening checklist (deferred for prototype)

- [ ] Lock down RLS: remove anon `UPDATE` on orders; add staff auth (Supabase magic-link)
- [ ] Move dashboard mark-ready/done writes behind authenticated role
- [ ] **UTR capture upgrade** (replaces blind trust): after "I've Paid", ask the student to paste the 12-digit UPI transaction ref shown in their app; store in `student_utr`, set status to a new `payment_claimed` state, and require a staff tap to confirm (cross-checked against the canteen's own bank/UPI app) before `assign_next_token` runs
- [ ] Rate-limit and validate `/pay/{txn_id}` — confirm `txn_id` matches a real `pending_payment` order before redirecting, so the route can't be used as an open redirect
- [ ] Cap "I've Paid" to one claim per order (idempotency) so a double-tap can't do anything twice
- [ ] Persist cart to DB (currently in-memory; lost on restart) if abandonment tracking is wanted
- [ ] Structured logging + error alerting
- [ ] Backups: Supabase free tier has limited backup retention — confirm before relying on it

---

## 12. Build order (for Claude Code)

1. **`schema.sql`** — write full DDL incl. `assign_next_token`, RLS policies, Realtime enable, seed menu. (Everything depends on this.)
2. **`config.py`** + **`db.py`** — env loading, Supabase REST wrapper.
3. **`bot.py`** — `/start`, menu browse, cart, confirm → insert order, build pay buttons, handle "I've Paid" callback → `assign_next_token` → notify.
4. **`upi.py`** — build the `upi://pay` deep link + QR PNG, no external calls.
5. **`server.py`** — `GET /pay/{txn_id}` (302 redirect to the deep link), `GET /health`.
6. **`main.py`** — wire bot + FastAPI into one event loop.
7. **`Dockerfile`, `fly.toml`, `.env.example`, `requirements.txt`.**
8. **`dashboard.html`** — static, Realtime subscription, staff queue + owner analytics.

---

## 13. Open decisions

- **Payment verification: blind trust, deliberately.** Going with a raw `upi://pay` link straight to the canteen's own VPA means no PG sits in the middle, so nothing can call the backend to confirm a payment happened — "I've Paid" is taken at face value. This was chosen over (a) a PG-based UPI Intent flow, which would restore automatic webhook verification but reintroduces a gateway/KYC dependency, and (b) asking for a UTR on every order up front, which adds friction to every single purchase. If abuse shows up in practice, the escalation path is the UTR-capture item in §11 — not necessarily switching back to a PG.
- **Polling vs webhook for the bot itself:** spec uses **polling** (simpler, Fly keeps it alive). Switch to Telegram webhooks only if latency becomes an issue. (Unrelated to the payment verification decision above — this is about how Telegram delivers bot updates.)
- **Staff dashboard auth:** open kiosk for now; magic-link later (§11).
- **Multi-canteen / SaaS:** out of scope until single-canteen is live. Schema already supports adding a `canteen_id` FK later without breaking changes.

---

## Quick references

- Supabase: https://supabase.com
- Telegram BotFather: https://t.me/BotFather
- python-telegram-bot v20 docs: https://docs.python-telegram-bot.org
- `qrcode` (Python) on PyPI: https://pypi.org/project/qrcode/
- Fly.io docs: https://fly.io/docs
- Chart.js v4: https://www.chartjs.org/docs/4.x
- @supabase/supabase-js v2: https://supabase.com/docs/reference/javascript
