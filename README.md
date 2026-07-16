# LineZero

A canteen pre-order system: Telegram bot menu + cart → pay via UPI deep link →
live staff dashboard. See [ARCHITECTURE_UPI_Deep_Linking_Prototype.md](ARCHITECTURE_UPI_Deep_Linking_Prototype.md)
for the full design.

## Setup

1. **Supabase**
   - Create a project at https://supabase.com.
   - Open the SQL editor and run `schema.sql` (creates tables, `assign_next_token`,
     RLS policies, enables Realtime on `orders`, and seeds the menu).
   - Copy the project URL, `anon` key, and `service_role` key from
     Project Settings → API.

2. **Telegram bot**
   - Already created via [@BotFather](https://t.me/BotFather): `@NHCKcanteen_bot`.

3. **UPI**
   - Decide the canteen's own UPI ID (e.g. `canteen@oksbi`) and a display name.
   - No PG, no KYC, no signup — see §8 of the architecture doc.

4. **Environment**
   - Copy `.env.example` to `.env` (a `.env` already exists locally with the bot
     token filled in — add the Supabase and UPI values to it).
   - `UPI_REDIRECT_BASE_URL` should point at wherever this service is reachable
     over HTTPS (your Fly.io app URL once deployed; for local testing, an ngrok/
     Cloudflare Tunnel URL, since Telegram's inline button needs a public HTTPS
     endpoint to redirect from).

5. **Install & run locally**
   ```
   python -m venv .venv
   .venv/Scripts/activate        # Windows
   pip install -r requirements.txt
   python -m app.main
   ```
   This starts the bot's polling loop and the FastAPI server (`/pay/{txn_id}`,
   `/health`) together on `PORT` (default 8080).

6. **Dashboard**
   - Open `dashboard.html`, fill in `SUPABASE_URL` and `SUPABASE_ANON_KEY` near
     the top of the `<script type="module">` block.
   - Deploy by dragging the file onto Netlify (or any static host) — no build step.

## Deploy (Fly.io)

```
fly launch
fly secrets set TELEGRAM_BOT_TOKEN=... SUPABASE_URL=... SUPABASE_SERVICE_ROLE_KEY=... UPI_VPA=... UPI_PAYEE_NAME=... UPI_REDIRECT_BASE_URL=...
fly deploy
```

`auto_stop_machines = false` and `min_machines_running = 1` in `fly.toml` keep the
bot's polling loop alive — do not change these.

## Payment verification posture

There is no gateway in this design — the deep link pays the canteen's own UPI ID
directly, so "I've Paid" in the bot is trusted at face value. See §11/§13 of the
architecture doc for the UTR-capture upgrade path if that becomes a problem.
