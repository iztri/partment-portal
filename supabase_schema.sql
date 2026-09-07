-- Marketing + BTL Apartment Portal — Safe Database Migration & Schema
-- Safe to run at any time: DOES NOT DROP TABLES OR DELETE EXISTING DATA.

-- 1. users table
create table if not exists users (
    id            bigint generated always as identity primary key,
    username      text not null unique,
    name          text not null default '',
    password_hash text not null default '',
    workspace     text not null default 'btl' check (workspace in ('marketing','btl')),
    is_admin      boolean not null default false,
    active        boolean not null default true,
    created_at    text not null default ''
);

alter table users add column if not exists is_admin boolean not null default false;
alter table users add column if not exists workspace text not null default 'btl';
alter table users add column if not exists active boolean not null default true;

-- 2. user_permissions table
create table if not exists user_permissions (
    id       bigint generated always as identity primary key,
    username text not null,
    feature  text not null,
    level    text not null default 'edit' check (level in ('none','read','edit')),
    unique (username, feature)
);
create index if not exists user_permissions_username_idx on user_permissions (username);

-- 3. hubs table & seed
create table if not exists hubs (
    hub_id     bigint primary key,
    hub_name   text not null unique,
    created_at text not null default ''
);

insert into hubs (hub_id, hub_name) values
    (0, 'Unmapped'),
    (1, 'Arekere'),
    (7, 'Brigade Omega'),
    (8, 'Elita Promenade'),
    (9, 'Nandi Citadel'),
    (12, 'Godrej E-city'),
    (11, 'Sattva Misty Charm'),
    (13, 'Brigade Meadows'),
    (28, 'Prestige Jindal City'),
    (20, 'Brigade Panorama'),
    (31, 'House of Hiranandani'),
    (32, 'Koramangala'),
    (33, 'Electronic City'),
    (34, 'Sobha Dream Acres'),
    (37, 'Adarsh Palm Retreat')
on conflict (hub_id) do nothing;

-- 4. apartments table & columns
create table if not exists apartments (
    id             bigint generated always as identity primary key,
    name           text not null default '',
    apartment_code text not null default '',
    hub            text not null default '',
    location_link  text not null default '',
    assigned_to    text not null default '',
    status         text not null default 'Pending',
    deleted        boolean not null default false,
    created_by     text not null default '',
    created_at     text not null default ''
);

alter table apartments add column if not exists apartment_code text not null default '';
alter table apartments add column if not exists deleted boolean not null default false;
alter table apartments add column if not exists status text not null default 'Pending';
alter table apartments add column if not exists assigned_to text not null default '';
alter table apartments add column if not exists hub text not null default '';
alter table apartments add column if not exists location_link text not null default '';
alter table apartments add column if not exists recollect_at text not null default '';

create index if not exists apartments_code_idx on apartments (apartment_code) where apartment_code <> '';
create index if not exists apartments_assigned_to_idx on apartments (assigned_to) where deleted = false;

-- 5. collections table
create table if not exists collections (
    id                    bigint generated always as identity primary key,
    apartment_id          bigint not null unique references apartments (id) on delete cascade,
    outcome               text not null default 'number' check (outcome in ('number','no_number')),
    contact_name          text not null default '',
    phone                 text not null default '',
    designation           text not null default '',
    total_units           integer not null default 0,
    no_number_reason      text not null default '',
    previous_contact_name text not null default '',
    previous_phone        text not null default '',
    previous_saved_at     text not null default '',
    collected_by          text not null default '',
    collected_at          text not null default '',
    updated_at            text not null default ''
);

alter table collections add column if not exists previous_contact_name text not null default '';
alter table collections add column if not exists previous_phone text not null default '';
alter table collections add column if not exists previous_saved_at text not null default '';

-- 6. collection_campaigns table
create table if not exists collection_campaigns (
    id            bigint generated always as identity primary key,
    collection_id bigint not null references collections (id) on delete cascade,
    campaign      text not null,
    price         double precision not null default 0,
    days          integer not null default 0
);
create index if not exists collection_campaigns_collection_idx on collection_campaigns (collection_id);

-- 7. standees table & columns
create table if not exists standees (
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

alter table standees add column if not exists photo_path text not null default '';
alter table standees add column if not exists active boolean not null default true;
alter table standees add column if not exists replaced_by bigint references standees (id);
alter table standees add column if not exists damaged_resolved integer not null default 0;
alter table standees add column if not exists created_by text not null default '';

-- 8. standee_reprints table
create table if not exists standee_reprints (
    id           bigint generated always as identity primary key,
    standee_id   bigint not null references standees (id) on delete cascade,
    added_units  integer not null default 0,
    note         text not null default '',
    added_by     text not null default '',
    added_at     text not null default ''
);
create index if not exists standee_reprints_standee_idx on standee_reprints (standee_id);

-- 9. standee_assignments table & columns
create table if not exists standee_assignments (
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
    quantity_missing     integer not null default 0,
    damage_note          text not null default '',
    drop_location        text not null default '',
    redeployed_to        bigint,
    invoice_photo        text not null default '',
    invoice_note         text not null default '',
    created_by           text not null default '',
    created_at           text not null default '',
    updated_at           text not null default ''
);

alter table standee_assignments add column if not exists quantity_missing integer not null default 0;
alter table standee_assignments add column if not exists redeployed_to bigint;
alter table standee_assignments add column if not exists damage_note text not null default '';
alter table standee_assignments add column if not exists drop_location text not null default '';
alter table standee_assignments add column if not exists quantity_returned integer not null default 0;
alter table standee_assignments add column if not exists quantity_damaged integer not null default 0;
alter table standee_assignments add column if not exists collect_by text not null default '';
alter table standee_assignments add column if not exists collected_at text not null default '';
alter table standee_assignments add column if not exists collected_by text not null default '';
alter table standee_assignments add column if not exists placed_at text not null default '';
alter table standee_assignments add column if not exists placed_by text not null default '';
alter table standee_assignments add column if not exists invoice_photo text not null default '';
alter table standee_assignments add column if not exists invoice_note text not null default '';
alter table standee_assignments add column if not exists updated_at text not null default '';

create index if not exists standee_assignments_assigned_to_idx on standee_assignments (assigned_to);
create index if not exists standee_assignments_status_idx on standee_assignments (status);

-- 10. standee_photos table
create table if not exists standee_photos (
    id              bigint generated always as identity primary key,
    assignment_id   bigint not null references standee_assignments (id) on delete cascade,
    kind            text not null default 'placement' check (kind in ('placement','damage')),
    path            text not null,
    uploaded_at     text not null default ''
);
create index if not exists standee_photos_assignment_idx on standee_photos (assignment_id);

-- 11. Ensure user gowtham exists and is admin (without deleting any other user)
insert into users (username, name, password_hash, workspace, is_admin, active, created_at)
values ('gowtham', 'Gowtham', 'pbkdf2:sha256:1000000$KDAxpOjN07lI4FMT$bc119260872e409c318b2f913395195178bd39c05bfb92fae606c1e648f8d85d', 'marketing', true, true, '')
on conflict (username) do update set
    is_admin = true,
    active = true;
