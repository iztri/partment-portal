CREATE TABLE IF NOT EXISTS apartments (
    id BIGSERIAL PRIMARY KEY,
    apartment_name TEXT NOT NULL,
    hub_name TEXT NOT NULL,
    location_link TEXT DEFAULT '',
    assigned_to TEXT DEFAULT '',
    assigned_date TEXT DEFAULT '',
    status TEXT DEFAULT 'Pending',
    created_by TEXT DEFAULT '',
    created_at TEXT DEFAULT '',
    notes_for_field TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS visits (
    id BIGSERIAL PRIMARY KEY,
    apartment_id BIGINT REFERENCES apartments(id),
    apartment_name TEXT DEFAULT '',
    hub_name TEXT DEFAULT '',
    manager_name TEXT DEFAULT '',
    no_of_units INTEGER DEFAULT 0,
    manager_phone TEXT DEFAULT '',
    channels_data TEXT DEFAULT '{}',
    notes TEXT DEFAULT '',
    visited_by TEXT DEFAULT '',
    visited_at TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS standees (
    id BIGSERIAL PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    total_units INTEGER DEFAULT 0,
    storage_location TEXT DEFAULT '',
    created_at TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS standee_assignments (
    id BIGSERIAL PRIMARY KEY,
    standee_id BIGINT REFERENCES standees(id),
    apartment_id BIGINT REFERENCES apartments(id),
    assigned_to TEXT DEFAULT '',
    start_date TEXT DEFAULT '',
    end_date TEXT DEFAULT '',
    quantity INTEGER DEFAULT 0,
    notes TEXT DEFAULT '',
    status TEXT DEFAULT 'Pending',
    placed_at TEXT DEFAULT '',
    removed_at TEXT DEFAULT '',
    damage_reported INTEGER DEFAULT 0,
    damage_details TEXT DEFAULT '',
    return_location TEXT DEFAULT '',
    collection_location TEXT DEFAULT '',
    created_at TEXT DEFAULT ''
);
