-- Marketing + BTL apartment campaign portal — Supabase schema & migration
-- Safe to run multiple times in the Supabase SQL editor.
-- Works on a fresh database OR upgrades an existing one without data loss.

-- 1. users table
create table if not exists users (
    id            bigint generated always as identity primary key,
    username      text not null unique,
    name          text not null default '',
    password_hash text not null,
    workspace     text not null default 'btl' check (workspace in ('marketing','btl')),
    active        boolean not null default true,
    created_at    text not null default ''
);

-- 2. apartments table (upgrade if exists, create if not)
create table if not exists apartments (
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

do $$
begin
  -- Rename apartment_name -> name if old column exists
  if exists (select 1 from information_schema.columns where table_name='apartments' and column_name='apartment_name') then
    alter table apartments rename column apartment_name to name;
  end if;
  -- Rename hub_name -> hub if old column exists
  if exists (select 1 from information_schema.columns where table_name='apartments' and column_name='hub_name') then
    alter table apartments rename column hub_name to hub;
  end if;
  -- Add deleted column if not exists
  if not exists (select 1 from information_schema.columns where table_name='apartments' and column_name='deleted') then
    alter table apartments add column deleted boolean not null default false;
  end if;
  -- Ensure defaults
  alter table apartments alter column name set default '';
  alter table apartments alter column hub set default '';
end $$;

create index if not exists apartments_assigned_to_idx on apartments (assigned_to) where deleted = false;

-- 3. collections table
create table if not exists collections (
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

-- 4. collection_campaigns table
create table if not exists collection_campaigns (
    id            bigint generated always as identity primary key,
    collection_id bigint not null references collections (id) on delete cascade,
    campaign      text not null,
    price         double precision not null default 0,
    days          integer not null default 0
);
create index if not exists collection_campaigns_collection_idx on collection_campaigns (collection_id);

-- 5. standees table (upgrade if exists, create if not)
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

do $$
begin
  if not exists (select 1 from information_schema.columns where table_name='standees' and column_name='photo_path') then
    alter table standees add column photo_path text not null default '';
  end if;
  if not exists (select 1 from information_schema.columns where table_name='standees' and column_name='active') then
    alter table standees add column active boolean not null default true;
  end if;
  if not exists (select 1 from information_schema.columns where table_name='standees' and column_name='replaced_by') then
    alter table standees add column replaced_by bigint references standees (id);
  end if;
  if not exists (select 1 from information_schema.columns where table_name='standees' and column_name='damaged_resolved') then
    alter table standees add column damaged_resolved integer not null default 0;
  end if;
  if not exists (select 1 from information_schema.columns where table_name='standees' and column_name='created_by') then
    alter table standees add column created_by text not null default '';
  end if;
end $$;

-- 6. standee_reprints
create table if not exists standee_reprints (
    id           bigint generated always as identity primary key,
    standee_id   bigint not null references standees (id) on delete cascade,
    added_units  integer not null default 0,
    note         text not null default '',
    added_by     text not null default '',
    added_at     text not null default ''
);
create index if not exists standee_reprints_standee_idx on standee_reprints (standee_id);

-- 7. standee_assignments (upgrade if exists, create if not)
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
    damage_note          text not null default '',
    drop_location        text not null default '',
    created_by           text not null default '',
    created_at           text not null default ''
);

do $$
begin
  if not exists (select 1 from information_schema.columns where table_name='standee_assignments' and column_name='duration_days') then
    alter table standee_assignments add column duration_days integer not null default 0;
  end if;
  if not exists (select 1 from information_schema.columns where table_name='standee_assignments' and column_name='placed_by') then
    alter table standee_assignments add column placed_by text not null default '';
  end if;
  if not exists (select 1 from information_schema.columns where table_name='standee_assignments' and column_name='collect_by') then
    alter table standee_assignments add column collect_by text not null default '';
  end if;
  if not exists (select 1 from information_schema.columns where table_name='standee_assignments' and column_name='collected_at') then
    alter table standee_assignments add column collected_at text not null default '';
  end if;
  if not exists (select 1 from information_schema.columns where table_name='standee_assignments' and column_name='collected_by') then
    alter table standee_assignments add column collected_by text not null default '';
  end if;
  if not exists (select 1 from information_schema.columns where table_name='standee_assignments' and column_name='quantity_returned') then
    alter table standee_assignments add column quantity_returned integer not null default 0;
  end if;
  if not exists (select 1 from information_schema.columns where table_name='standee_assignments' and column_name='quantity_damaged') then
    alter table standee_assignments add column quantity_damaged integer not null default 0;
  end if;
  if not exists (select 1 from information_schema.columns where table_name='standee_assignments' and column_name='damage_note') then
    alter table standee_assignments add column damage_note text not null default '';
  end if;
  if not exists (select 1 from information_schema.columns where table_name='standee_assignments' and column_name='drop_location') then
    alter table standee_assignments add column drop_location text not null default '';
  end if;
  -- If end_date existed from previous schema, migrate to collect_by
  if exists (select 1 from information_schema.columns where table_name='standee_assignments' and column_name='end_date') then
    update standee_assignments set collect_by = end_date where (collect_by is null or collect_by = '') and end_date is not null and end_date != '';
  end if;
end $$;

create index if not exists standee_assignments_assigned_to_idx on standee_assignments (assigned_to);
create index if not exists standee_assignments_status_idx on standee_assignments (status);

-- 8. standee_photos
create table if not exists standee_photos (
    id              bigint generated always as identity primary key,
    assignment_id   bigint not null references standee_assignments (id) on delete cascade,
    kind            text not null default 'placement' check (kind in ('placement','damage')),
    path            text not null,
    uploaded_at     text not null default ''
);
create index if not exists standee_photos_assignment_idx on standee_photos (assignment_id);
