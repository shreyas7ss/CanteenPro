-- LineZero schema. Run in the Supabase SQL editor.

create extension if not exists pgcrypto;

create table menu_items (
    id uuid primary key default gen_random_uuid(),
    name text not null,
    price numeric(10, 2) not null,
    category text not null,
    is_available boolean not null default true,
    image_url text,
    created_at timestamptz not null default now()
);

create table orders (
    id uuid primary key default gen_random_uuid(),
    token_number int,
    telegram_user_id bigint not null,
    telegram_username text,
    student_name text,
    roll_number text,
    total_amount numeric(10, 2) not null,
    merchant_transaction_id text not null unique,
    student_utr text,
    payment_mode text,
    status text not null default 'pending_payment'
        check (status in ('pending_payment', 'paid', 'ready', 'completed', 'cancelled')),
    notes text,
    placed_at timestamptz not null default now(),
    paid_at timestamptz,
    ready_at timestamptz,
    completed_at timestamptz
);

create table order_items (
    id uuid primary key default gen_random_uuid(),
    order_id uuid not null references orders (id) on delete cascade,
    menu_item_id uuid not null references menu_items (id),
    item_name text not null,
    unit_price numeric(10, 2) not null,
    quantity int not null check (quantity > 0)
);

create index orders_status_idx on orders (status);
create index order_items_order_id_idx on order_items (order_id);

-- Assigns the next per-day token number when a student confirms payment.
-- Idempotent: a repeat call on an already-paid order returns the same token
-- instead of burning a second one (guards against a double "I've Paid" tap).
-- Transaction-safe: an advisory lock serializes concurrent callers so two
-- simultaneous payments can never receive the same token.
create or replace function assign_next_token(p_order_id uuid)
returns int
language plpgsql
as $$
declare
    v_status text;
    v_existing_token int;
    v_token int;
begin
    select status, token_number into v_status, v_existing_token
    from orders
    where id = p_order_id
    for update;

    if not found then
        raise exception 'order % not found', p_order_id;
    end if;

    if v_status in ('paid', 'ready', 'completed') then
        return v_existing_token;
    end if;

    perform pg_advisory_xact_lock(hashtext('linezero_token_' || current_date::text));

    select count(*) + 1 into v_token
    from orders
    where status in ('paid', 'ready', 'completed')
      and paid_at::date = current_date;

    update orders
    set status = 'paid',
        token_number = v_token,
        paid_at = now()
    where id = p_order_id;

    return v_token;
end;
$$;

-- RLS (prototype posture — see §6, §11 of the architecture doc)
alter table menu_items enable row level security;
alter table orders enable row level security;
alter table order_items enable row level security;

create policy "anon can read menu_items" on menu_items
    for select using (true);

create policy "anon can read orders" on orders
    for select using (true);

create policy "anon can update orders" on orders
    for update using (true) with check (true);

create policy "anon can read order_items" on order_items
    for select using (true);

-- Realtime: dashboard subscribes to changes on orders.
alter publication supabase_realtime add table orders;

-- Seed menu
insert into menu_items (name, price, category) values
    ('Vada Pav', 20.00, 'Snacks'),
    ('Samosa', 15.00, 'Snacks'),
    ('Veg Sandwich', 40.00, 'Snacks'),
    ('Masala Maggi', 35.00, 'Snacks'),
    ('Idli Sambar', 45.00, 'Meals'),
    ('Veg Thali', 80.00, 'Meals'),
    ('Chai', 10.00, 'Beverages'),
    ('Cold Coffee', 40.00, 'Beverages'),
    ('Bottled Water', 20.00, 'Beverages');
