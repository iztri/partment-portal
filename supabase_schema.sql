-- Marketing + BTL apartment campaign portal — Supabase schema
-- Run once in the Supabase SQL editor for a fresh project.

create table if not exists users (
    id            bigint generated always as identity primary key,
    username      text not null unique,
    name          text not null default '',
    password_hash text not null,
    workspace     text not null default 'btl' check (workspace in ('marketing','btl')),
    active        boolean not null default true,
    created_at    text not null default ''
);

create table if not exists apartments (
    id            bigint generated always as identity primary key,
    name          text not null,
    hub           text not null default '',
    location_link text not null default '',
    assigned_to   text not null default '',
    status        text not null default 'Pending',
    deleted       boolean not null default false,
    created_by    text not null default '',
    created_at    text not null default ''
);
create index if not exists apartments_assigned_to_idx on apartments (assigned_to) where deleted = false;

create table if not exists collections (
    id               bigint generated always as identity primary key,
    apartment_id     bigint not null unique references apartments (id) on delete cascade,
    outcome          text not null default 'number' check (outcome in ('number','no_number')),
    phone            text not null default '',
    designation      text not null default '',
    no_number_reason text not null default '',
    collected_by     text not null default '',
    collected_at     text not null default '',
    updated_at       text not null default ''
);

create table if not exists collection_campaigns (
    id            bigint generated always as identity primary key,
    collection_id bigint not null references collections (id) on delete cascade,
    campaign      text not null,
    price         double precision not null default 0,
    days          integer not null default 0
);
create index if not exists collection_campaigns_collection_idx on collection_campaigns (collection_id);
