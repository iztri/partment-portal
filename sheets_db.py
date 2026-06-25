"""Supabase database layer for apartment portal."""

import json
from datetime import datetime, timezone, timedelta
from supabase import create_client

IST = timezone(timedelta(hours=5, minutes=30))

def _now_ist():
    return datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S")
from config import SUPABASE_URL, SUPABASE_KEY


# ── Column maps between Supabase (snake_case) and app dict keys ────────
APARTMENT_COL_MAP = {
    "id": "Apartment ID",
    "apartment_name": "Apartment Name",
    "hub_name": "Hub Name",
    "location_link": "Location Link",
    "assigned_to": "Assigned To",
    "assigned_date": "Assigned Date",
    "status": "Status",
    "created_by": "Created By",
    "created_at": "Created At",
}
APARTMENT_REVERSE = {v: k for k, v in APARTMENT_COL_MAP.items()}

VISIT_COL_MAP = {
    "id": "Visit ID",
    "apartment_id": "Apartment ID",
    "apartment_name": "Apartment Name",
    "hub_name": "Hub Name",
    "manager_name": "Manager Name",
    "no_of_units": "No of Units",
    "manager_phone": "Manager Phone",
    "channels_data": "Channels Data (JSON)",
    "notes": "Notes",
    "visited_by": "Visited By",
    "visited_at": "Visited At",
}
VISIT_REVERSE = {v: k for k, v in VISIT_COL_MAP.items()}


def _row_to_dict(row, col_map):
    """Convert a Supabase row dict to the app's dict keys."""
    return {col_map.get(k, k): v for k, v in row.items() if k in col_map}


def _rows_to_list(rows, col_map):
    return [_row_to_dict(r, col_map) for r in rows]


def _app_keys_to_db(data, reverse_map):
    """Convert app dict keys back to Supabase column names."""
    return {reverse_map.get(k, k): v for k, v in data.items() if k in reverse_map}


class SheetsDB:
    def __init__(self):
        self.supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

    # ── Apartments ──────────────────────────────────────────────────────
    def add_apartment(self, name, hub_name, location_link, created_by):
        now = _now_ist()
        data = {
            "apartment_name": name,
            "hub_name": hub_name,
            "location_link": location_link,
            "assigned_to": "",
            "assigned_date": "",
            "status": "Pending",
            "created_by": created_by,
            "created_at": now,
        }
        result = self.supabase.table("apartments").insert(data).execute()
        return result.data[0]["id"] if result.data else None

    def get_apartments(self, status=None, assigned_to=None, date=None):
        query = self.supabase.table("apartments").select("*")
        if status:
            query = query.eq("status", status)
        if assigned_to:
            query = query.eq("assigned_to", assigned_to)
        if date:
            query = query.eq("assigned_date", date)
        result = query.execute()
        return _rows_to_list(result.data, APARTMENT_COL_MAP)

    def get_all_apartments(self):
        result = self.supabase.table("apartments").select("*").execute()
        return _rows_to_list(result.data, APARTMENT_COL_MAP)

    def assign_apartments(self, apartment_ids, assigned_to, assigned_date):
        ids = [int(x) for x in apartment_ids]
        for aid in ids:
            self.supabase.table("apartments").update({
                "assigned_to": assigned_to,
                "assigned_date": assigned_date,
                "status": "Pending",
            }).eq("id", aid).execute()

    def update_apartment(self, apartment_id, **kwargs):
        updates = _app_keys_to_db(kwargs, APARTMENT_REVERSE)
        if updates:
            self.supabase.table("apartments").update(updates).eq("id", int(apartment_id)).execute()

    # ── Visits ──────────────────────────────────────────────────────────
    def record_visit(self, apartment_id, apartment_name, hub_name,
                     manager_name, no_of_units, manager_phone,
                     channels_data, notes, visited_by):
        now = _now_ist()
        data = {
            "apartment_id": int(apartment_id),
            "apartment_name": apartment_name,
            "hub_name": hub_name,
            "manager_name": manager_name,
            "no_of_units": int(no_of_units) if no_of_units else 0,
            "manager_phone": manager_phone,
            "channels_data": channels_data if isinstance(channels_data, (dict, list)) else json.loads(channels_data) if isinstance(channels_data, str) else {},
            "notes": notes or "",
            "visited_by": visited_by,
            "visited_at": now,
        }
        result = self.supabase.table("visits").insert(data).execute()
        self.update_apartment(apartment_id, Status="Visited")
        return result.data[0]["id"] if result.data else None

    def get_visits(self, apartment_id=None):
        query = self.supabase.table("visits").select("*")
        if apartment_id:
            query = query.eq("apartment_id", int(apartment_id))
        result = query.execute()
        return _rows_to_list(result.data, VISIT_COL_MAP)

    # ── Field team: get assignments ─────────────────────────────────────
    def get_assigned_for_user(self, username, date=None):
        query = self.supabase.table("apartments").select("*").eq("assigned_to", username)
        if date:
            query = query.eq("assigned_date", date)
        result = query.execute()
        return _rows_to_list(result.data, APARTMENT_COL_MAP)

    def get_available_dates_for_user(self, username):
        result = self.supabase.table("apartments").select("assigned_date").eq("assigned_to", username).neq("assigned_date", "").execute()
        dates = set()
        for r in result.data:
            if r.get("assigned_date"):
                dates.add(r["assigned_date"])
        return sorted(dates)
