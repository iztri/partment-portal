-- Marketing + BTL apartment campaign portal — Fresh Supabase schema
-- Run this in the Supabase SQL editor to create a clean database.

-- Drop old tables if they exist
drop table if exists visits cascade;
drop table if exists standee_photos cascade;
drop table if exists standee_reprints cascade;
drop table if exists standee_assignments cascade;
drop table if exists standees cascade;
drop table if exists collection_campaigns cascade;
drop table if exists collections cascade;
drop table if exists apartments cascade;
drop table if exists users cascade;

-- 1. users
create table users (
    id            bigint generated always as identity primary key,
    username      text not null unique,
    name          text not null default '',
    password_hash text not null,
    workspace     text not null default 'btl' check (workspace in ('marketing','btl')),
    active        boolean not null default true,
    created_at    text not null default ''
);

-- 2. apartments
create table apartments (
    id            bigint generated always as identity primary key,
    name          text not null default '',
    hub           text not null default '',
    location_link text not null default '',
    assigned_to   text not null default '',
    status        text not null default 'Pending',
    deleted       boolean not null default false,
    created_by    text not null default '',
    created_at    text not null default ''
);
create index apartments_assigned_to_idx on apartments (assigned_to) where deleted = false;

-- 3. collections
create table collections (
    id               bigint generated always as identity primary key,
    apartment_id     bigint not null unique references apartments (id) on delete cascade,
    outcome          text not null default 'number' check (outcome in ('number','no_number')),
    contact_name     text not null default '',
    phone            text not null default '',
    designation      text not null default '',
    total_units      integer not null default 0,
    no_number_reason text not null default '',
    collected_by     text not null default '',
    collected_at     text not null default '',
    updated_at       text not null default ''
);

-- 4. collection_campaigns
create table collection_campaigns (
    id            bigint generated always as identity primary key,
    collection_id bigint not null references collections (id) on delete cascade,
    campaign      text not null,
    price         double precision not null default 0,
    days          integer not null default 0
);
create index collection_campaigns_collection_idx on collection_campaigns (collection_id);

-- 5. standees
create table standees (
    id                bigint generated always as identity primary key,
    name              text not null unique,
    photo_path        text not null default '',
    total_units       integer not null default 0,
    storage_location  text not null default '',
    active            boolean not null default true,
    replaced_by       bigint references standees (id),
    damaged_resolved  integer not null default 0,
    created_by        text not null default '',
    created_at        text not null default ''
);

-- 6. standee_reprints
create table standee_reprints (
    id           bigint generated always as identity primary key,
    standee_id   bigint not null references standees (id) on delete cascade,
    added_units  integer not null default 0,
    note         text not null default '',
    added_by     text not null default '',
    added_at     text not null default ''
);
create index standee_reprints_standee_idx on standee_reprints (standee_id);

-- 7. standee_assignments
create table standee_assignments (
    id                   bigint generated always as identity primary key,
    standee_id           bigint not null references standees (id),
    apartment_id         bigint not null references apartments (id),
    assigned_to          text not null default '',
    quantity             integer not null default 0,
    duration_days        integer not null default 0,
    collection_location  text not null default '',
    status               text not null default 'Assigned' check (status in ('Assigned','Placed','Collected')),
    placed_at            text not null default '',
    placed_by            text not null default '',
    collect_by           text not null default '',
    collected_at         text not null default '',
    collected_by         text not null default '',
    quantity_returned    integer not null default 0,
    quantity_damaged     integer not null default 0,
    damage_note          text not null default '',
    drop_location        text not null default '',
    created_by           text not null default '',
    created_at           text not null default ''
);
create index standee_assignments_assigned_to_idx on standee_assignments (assigned_to);
create index standee_assignments_status_idx on standee_assignments (status);

-- 8. standee_photos
create table standee_photos (
    id              bigint generated always as identity primary key,
    assignment_id   bigint not null references standee_assignments (id) on delete cascade,
    kind            text not null default 'placement' check (kind in ('placement','damage')),
    path            text not null,
    uploaded_at     text not null default ''
);
create index standee_photos_assignment_idx on standee_photos (assignment_id);

-- 9. Seed single admin user
delete from users;
insert into users (username, name, password_hash, workspace, active, created_at)
values ('gowtham', 'Gowtham', 'pbkdf2:sha256:1000000$KDAxpOjN07lI4FMT$bc119260872e409c318b2f913395195178bd39c05bfb92fae606c1e648f8d85d', 'marketing', true, '');
