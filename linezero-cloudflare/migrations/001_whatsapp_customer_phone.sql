-- Add WhatsApp identity to existing orders without removing historical Telegram data.
alter table orders
    add column if not exists customer_phone text;

-- Legacy rows still need their old required column satisfied by PostgREST inserts.
alter table orders
    alter column telegram_user_id set default 0;

create index if not exists orders_customer_phone_idx on orders (customer_phone);
