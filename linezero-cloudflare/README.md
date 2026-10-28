# LineZero Ordering Site

This folder is a standalone Cloudflare Pages app. It contains only the website,
its Pages Functions, and the assets needed to deploy it; it does not depend on
the parent CanteenPro repository or its Git submodule.

## New repository and Pages setup

1. Create a new, empty GitHub repository. Copy the **contents** of this folder
   into that repository's root and push them to the `main` branch.
2. In Cloudflare, create a **Pages** project connected to the new repository.
   Set framework preset to **None**, build command to blank, and build output
   directory to `static`. Leave the root directory blank because this is now
   the repository root. Use `main` as the production branch.
3. Add these production variables and secrets in the Pages project settings:
   - `SUPABASE_URL` (variable)
   - `SUPABASE_SERVICE_ROLE_KEY` (secret)
   - `UPI_VPA` (secret or variable)
   - `UPI_PAYEE_NAME` (variable)
4. Deploy. Do not put Wrangler commands in the Pages build command; Cloudflare
   builds and deploys the project itself.

The database must already have the LineZero schema and menu in Supabase. The
service-role key is used only by Pages Functions and is never sent to browsers.

## Order flow

The root URL serves the order site. `/api/menu`, `/api/orders`, and
`/pay/{transaction_id}` are implemented by Pages Functions. Website orders
collect a student name and roll number, then open a UPI payment link. WhatsApp
chat ordering runs in the separate FastAPI service and
uses the GetGabs inbound webhook.

Set `UPI_REDIRECT_BASE_URL` in the API runtime environment to this Pages origin,
such as `https://linezero-ordering-site.pages.dev`. The `/app` rewrite serves
the ordering page.

For an existing Supabase database, run
`migrations/001_whatsapp_customer_phone.sql` before deploying the updated API.
Configure GetGabs to deliver inbound messages to
`https://<your-api-host>/wa/webhook?token=<GETGABS_WEBHOOK_TOKEN>`. Keep both
`GETGABS_API_KEY` and a separate random `GETGABS_WEBHOOK_TOKEN` in the API
runtime's secret store, not the Pages project.
GetGabs service messages are intended for replies in an active customer service
conversation; use approved WhatsApp templates for business-initiated messages
outside that window. Bulk campaigns are not included, and web checkout does not
send WhatsApp messages.

Before accepting public traffic, configure rate limiting for `/api/orders`.