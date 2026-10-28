# LineZero standalone website

This folder can be deployed as a Cloudflare Pages project. The menu and checkout
use Pages Functions, so the Supabase service-role key stays on the server and
is never sent to the browser.

## Cloudflare Pages

### Git integration (recommended)

1. In Cloudflare Pages, create a project connected to this repository. Set the
   root directory to `app`, the production branch to your branch (usually
   `main`), the framework preset to **None**, the build command to blank, and
   the build output directory to `static`.
2. Do not put `wrangler pages project create` or `wrangler pages deploy` in the
   build command. Cloudflare builds and deploys the Pages project itself; those
   commands are only for manual deployment.
3. Add these settings under **Settings > Variables and Secrets** for production
   (and preview too, if you use preview deployments):
   - `SUPABASE_URL` (variable)
   - `SUPABASE_SERVICE_ROLE_KEY` (secret)
   - `UPI_VPA` (secret or variable)
   - `UPI_PAYEE_NAME` (variable)

### Manual Wrangler deployment

Run these commands locally from this `app` folder, not as a Cloudflare Pages
build command:

   ```powershell
   npx wrangler login
   npx wrangler pages project create linezero --production-branch main
   npx wrangler pages deploy ./static --project-name linezero
   ```

Skip the `project create` command if the project already exists. If using
`CLOUDFLARE_API_TOKEN` instead of `wrangler login`, the token needs **Account >
Cloudflare Pages > Edit** permission for the account containing the project.
Set the same variables and secrets in the Pages project before testing checkout.

Set `UPI_REDIRECT_BASE_URL` in the API runtime environment to the Pages origin
(for example, `https://linezero.pages.dev`). The `/app` rewrite serves the
ordering page, and the Pages payment route handles UPI redirects.

The root URL serves the ordering site. `/api/menu`, `/api/orders`, and
`/pay/{transaction_id}` are implemented by Pages Functions. Browser orders
collect a student name and roll number, then open a UPI payment link. WhatsApp
chat ordering and replies run in the FastAPI service;
configure GetGabs to deliver inbound message webhooks to
`https://<your-api-host>/wa/webhook?token=<GETGABS_WEBHOOK_TOKEN>`. Set both
`GETGABS_API_KEY` and a separate random `GETGABS_WEBHOOK_TOKEN` in the FastAPI
runtime's secret store.

WhatsApp replies cover customer-started chats and order actions; standalone
website orders are not sent a WhatsApp message. Bulk campaigns are not part of
this integration.

For an existing Supabase database, run `migrations/001_whatsapp_customer_phone.sql`
before deploying the updated API. Never expose either GetGabs secret to Pages
or the browser. GetGabs service messages
are intended for replies in an active customer service conversation. Use an
approved WhatsApp template for business-initiated notifications outside that
window.

The existing FastAPI deployment remains supported. Run it from the repository
root as before; it serves the same ordering page and implements `/api/menu`.
Before accepting public traffic, add a Cloudflare rate-limit rule for
`/api/orders` to discourage automated order spam.