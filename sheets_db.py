"""Database layer — uses SQLite locally, Supabase on Render."""

import json
import os
import sqlite3
from datetime import datetime, timezone, timedelta
from supabase import create_client

IST = timezone(timedelta(hours=5, minutes=30))


def _now_ist():
    return datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S")


# ═══════════════════════════════════════════════════════════════════════
#  SQLite backend (local dev)
# ═══════════════════════════════════════════════════════════════════════
class _SQLiteDB:
    def __init__(self, db_path="local_dev.db"):
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self._init_tables()

    def _init_tables(self):
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS apartments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                apartment_name TEXT NOT NULL,
                hub_name TEXT NOT NULL,
                location_link TEXT DEFAULT '',
                assigned_to TEXT DEFAULT '',
                assigned_date TEXT DEFAULT '',
                status TEXT DEFAULT 'Pending',
                created_by TEXT DEFAULT '',
                created_at TEXT DEFAULT ''
            );
            CREATE TABLE IF NOT EXISTS visits (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                apartment_id INTEGER REFERENCES apartments(id),
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
        """)
        self.conn.commit()

    def add_apartment(self, name, hub_name, location_link, created_by):
        now = _now_ist()
        cur = self.conn.execute(
            "INSERT INTO apartments (apartment_name, hub_name, location_link, assigned_to, assigned_date, status, created_by, created_at) "
            "VALUES (?, ?, ?, '', '', 'Pending', ?, ?)",
            (name, hub_name, location_link, created_by, now),
        )
        self.conn.commit()
        return cur.lastrowid

    def get_apartments(self, status=None, assigned_to=None, date=None):
        sql = "SELECT * FROM apartments WHERE 1=1"
        params = []
        if status:
            sql += " AND status=?"
            params.append(status)
        if assigned_to:
            sql += " AND assigned_to=?"
            params.append(assigned_to)
        if date:
            sql += " AND assigned_date=?"
            params.append(date)
        sql += " ORDER BY id DESC"
        return [self._apt_row(r) for r in self.conn.execute(sql, params).fetchall()]

    def get_all_apartments(self):
        rows = self.conn.execute("SELECT * FROM apartments ORDER BY id DESC").fetchall()
        return [self._apt_row(r) for r in rows]

    def assign_apartments(self, apartment_ids, assigned_to, assigned_date):
        ids = [int(x) for x in apartment_ids]
        for aid in ids:
            self.conn.execute(
                "UPDATE apartments SET assigned_to=?, assigned_date=?, status='Pending' WHERE id=?",
                (assigned_to, assigned_date, aid),
            )
        self.conn.commit()

    def update_apartment(self, apartment_id, **kwargs):
        mapping = {
            "Apartment Name": "apartment_name",
            "Hub Name": "hub_name",
            "Location Link": "location_link",
            "Assigned To": "assigned_to",
            "Assigned Date": "assigned_date",
            "Status": "status",
            "Created By": "created_by",
            "Created At": "created_at",
        }
        cols = []
        vals = []
        for app_key, db_col in mapping.items():
            if app_key in kwargs:
                cols.append(f"{db_col}=?")
                vals.append(kwargs[app_key])
        if cols:
            vals.append(int(apartment_id))
            self.conn.execute(
                f"UPDATE apartments SET {', '.join(cols)} WHERE id=?", vals
            )
            self.conn.commit()

    def record_visit(self, apartment_id, apartment_name, hub_name,
                     manager_name, no_of_units, manager_phone,
                     channels_data, notes, visited_by):
        now = _now_ist()
        cd = json.dumps(channels_data, ensure_ascii=False) if isinstance(channels_data, (dict, list)) else str(channels_data or "{}")
        cur = self.conn.execute(
            "INSERT INTO visits (apartment_id, apartment_name, hub_name, manager_name, no_of_units, "
            "manager_phone, channels_data, notes, visited_by, visited_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (int(apartment_id), apartment_name, hub_name,
             manager_name, int(no_of_units) if no_of_units else 0,
             manager_phone, cd, notes or "", visited_by, now),
        )
        self.conn.commit()
        self.update_apartment(apartment_id, Status="Visited")
        return cur.lastrowid

    def get_visits(self, apartment_id=None):
        if apartment_id:
            rows = self.conn.execute(
                "SELECT * FROM visits WHERE apartment_id=? ORDER BY id DESC", (int(apartment_id),)
            ).fetchall()
        else:
            rows = self.conn.execute("SELECT * FROM visits ORDER BY id DESC").fetchall()
        return [self._visit_row(r) for r in rows]

    def get_assigned_for_user(self, username, date=None):
        sql = "SELECT * FROM apartments WHERE assigned_to=?"
        params = [username]
        if date:
            sql += " AND assigned_date=?"
            params.append(date)
        sql += " ORDER BY id DESC"
        return [self._apt_row(r) for r in self.conn.execute(sql, params).fetchall()]

    def get_available_dates_for_user(self, username):
        rows = self.conn.execute(
            "SELECT DISTINCT assigned_date FROM apartments WHERE assigned_to=? AND assigned_date!='' ORDER BY assigned_date",
            (username,),
        ).fetchall()
        return [r["assigned_date"] for r in rows]

    # ── helpers ──
    def _apt_row(self, r):
        return {
            "Apartment ID": r["id"],
            "Apartment Name": r["apartment_name"],
            "Hub Name": r["hub_name"],
            "Location Link": r["location_link"],
            "Assigned To": r["assigned_to"],
            "Assigned Date": r["assigned_date"],
            "Status": r["status"],
            "Created By": r["created_by"],
            "Created At": r["created_at"],
        }

    def _visit_row(self, r):
        return {
            "Visit ID": r["id"],
            "Apartment ID": r["apartment_id"],
            "Apartment Name": r["apartment_name"],
            "Hub Name": r["hub_name"],
            "Manager Name": r["manager_name"],
            "No of Units": r["no_of_units"],
            "Manager Phone": r["manager_phone"],
            "Channels Data (JSON)": r["channels_data"],
            "Notes": r["notes"],
            "Visited By": r["visited_by"],
            "Visited At": r["visited_at"],
        }


# ═══════════════════════════════════════════════════════════════════════
#  Supabase backend (production on Render)
# ═══════════════════════════════════════════════════════════════════════
class _SupabaseDB:
    def __init__(self):
        self.supabase = create_client(
            "https://ppxyhlmlymvhrjdcnoks.supabase.co",
            "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InBweHlobG1seW12aHJqZGNub2tzIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc4MjM2MzY1NCwiZXhwIjoyMDk3OTM5NjU0fQ.D7QZbfzpZKtutgo4lp4F8R15HNlzQAf7N3ApBz6GQ6s"
        )

    def add_apartment(self, name, hub_name, location_link, created_by):
        data = {
            "apartment_name": name,
            "hub_name": hub_name,
            "location_link": location_link,
            "assigned_to": "",
            "assigned_date": "",
            "status": "Pending",
            "created_by": created_by,
            "created_at": _now_ist(),
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
        return self._apt_rows(result.data)

    def get_all_apartments(self):
        result = self.supabase.table("apartments").select("*").order("id", desc=True).execute()
        return self._apt_rows(result.data)

    def assign_apartments(self, apartment_ids, assigned_to, assigned_date):
        for aid in (int(x) for x in apartment_ids):
            self.supabase.table("apartments").update({
                "assigned_to": assigned_to,
                "assigned_date": assigned_date,
                "status": "Pending",
            }).eq("id", aid).execute()

    def update_apartment(self, apartment_id, **kwargs):
        mapping = {
            "Apartment Name": "apartment_name",
            "Hub Name": "hub_name",
            "Location Link": "location_link",
            "Assigned To": "assigned_to",
            "Assigned Date": "assigned_date",
            "Status": "status",
        }
        updates = {mapping[k]: v for k, v in kwargs.items() if k in mapping}
        if updates:
            self.supabase.table("apartments").update(updates).eq("id", int(apartment_id)).execute()

    def record_visit(self, apartment_id, apartment_name, hub_name,
                     manager_name, no_of_units, manager_phone,
                     channels_data, notes, visited_by):
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
            "visited_at": _now_ist(),
        }
        result = self.supabase.table("visits").insert(data).execute()
        self.update_apartment(apartment_id, Status="Visited")
        return result.data[0]["id"] if result.data else None

    def get_visits(self, apartment_id=None):
        query = self.supabase.table("visits").select("*").order("id", desc=True)
        if apartment_id:
            query = query.eq("apartment_id", int(apartment_id))
        result = query.execute()
        return self._visit_rows(result.data)

    def get_assigned_for_user(self, username, date=None):
        query = self.supabase.table("apartments").select("*").eq("assigned_to", username).order("id", desc=True)
        if date:
            query = query.eq("assigned_date", date)
        result = query.execute()
        return self._apt_rows(result.data)

    def get_available_dates_for_user(self, username):
        result = self.supabase.table("apartments").select("assigned_date").eq("assigned_to", username).neq("assigned_date", "").execute()
        dates = set()
        for r in result.data:
            if r.get("assigned_date"):
                dates.add(r["assigned_date"])
        return sorted(dates)

    # ── helpers ──
    def _apt_rows(self, data):
        return [{
            "Apartment ID": r["id"],
            "Apartment Name": r["apartment_name"],
            "Hub Name": r["hub_name"],
            "Location Link": r["location_link"],
            "Assigned To": r["assigned_to"],
            "Assigned Date": r["assigned_date"],
            "Status": r["status"],
            "Created By": r["created_by"],
            "Created At": r["created_at"],
        } for r in data]

    def _visit_rows(self, data):
        return [{
            "Visit ID": r["id"],
            "Apartment ID": r["apartment_id"],
            "Apartment Name": r["apartment_name"],
            "Hub Name": r["hub_name"],
            "Manager Name": r["manager_name"],
            "No of Units": r["no_of_units"],
            "Manager Phone": r["manager_phone"],
            "Channels Data (JSON)": r["channels_data"],
            "Notes": r["notes"],
            "Visited By": r["visited_by"],
            "Visited At": r["visited_at"],
        } for r in data]


# ═══════════════════════════════════════════════════════════════════════
#  Public factory — SQLite locally, Supabase on Render
# ═══════════════════════════════════════════════════════════════════════
class SheetsDB:
    def __init__(self):
        if os.environ.get("RENDER"):
            self._impl = _SupabaseDB()
        else:
            self._impl = _SQLiteDB()

    def __getattr__(self, name):
        return getattr(self._impl, name)
