"""Database layer — uses SQLite locally, Supabase on Render."""

import json
import os
import sqlite3
import requests
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
                created_at TEXT DEFAULT '',
                notes_for_field TEXT DEFAULT ''
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
            CREATE TABLE IF NOT EXISTS standees (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                total_units INTEGER DEFAULT 0,
                storage_location TEXT DEFAULT '',
                created_at TEXT DEFAULT ''
            );
            CREATE TABLE IF NOT EXISTS standee_assignments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                standee_id INTEGER REFERENCES standees(id),
                apartment_id INTEGER REFERENCES apartments(id),
                assigned_to TEXT DEFAULT '',
                start_date TEXT DEFAULT '',
                end_date TEXT DEFAULT '',
                quantity INTEGER DEFAULT 0,
                notes TEXT DEFAULT '',
                status TEXT DEFAULT 'Pending',
                placed_at TEXT DEFAULT '',
                removed_at TEXT DEFAULT '',
                created_at TEXT DEFAULT ''
            );
        """)
        self.conn.commit()
        # migrate existing tables if column missing
        try:
            self.conn.execute("ALTER TABLE apartments ADD COLUMN notes_for_field TEXT DEFAULT ''")
        except:
            pass
        try:
            self.conn.execute("ALTER TABLE standee_assignments ADD COLUMN assigned_to TEXT DEFAULT ''")
            self.conn.execute("ALTER TABLE standee_assignments ADD COLUMN status TEXT DEFAULT 'Pending'")
            self.conn.execute("ALTER TABLE standee_assignments ADD COLUMN placed_at TEXT DEFAULT ''")
            self.conn.execute("ALTER TABLE standee_assignments ADD COLUMN removed_at TEXT DEFAULT ''")
        except:
            pass

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
        rows = self.conn.execute("SELECT * FROM apartments WHERE status!='Deleted' ORDER BY id DESC").fetchall()
        return [self._apt_row(r) for r in rows]

    def assign_apartments(self, apartment_ids, assigned_to, assigned_date, notes_for_field=""):
        ids = [int(x) for x in apartment_ids]
        for aid in ids:
            self.conn.execute(
                "UPDATE apartments SET assigned_to=?, assigned_date=?, notes_for_field=?, status='Pending' WHERE id=?",
                (assigned_to, assigned_date, notes_for_field, aid),
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
            "Notes for Field": "notes_for_field",
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

    def delete_apartment(self, apartment_id):
        self.conn.execute("UPDATE apartments SET status='Deleted' WHERE id=?", (int(apartment_id),))
        self.conn.commit()

    def restore_apartment(self, apartment_id):
        self.conn.execute("UPDATE apartments SET status='Pending' WHERE id=?", (int(apartment_id),))
        self.conn.commit()

    def get_deleted_apartments(self):
        rows = self.conn.execute("SELECT * FROM apartments WHERE status='Deleted' ORDER BY id DESC").fetchall()
        return [self._apt_row(r) for r in rows]

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

    # ── Standees ──
    def add_standee(self, name, total_units, storage_location):
        now = _now_ist()
        try:
            cur = self.conn.execute(
                "INSERT INTO standees (name, total_units, storage_location, created_at) VALUES (?, ?, ?, ?)",
                (name.strip(), int(total_units) if total_units else 0, storage_location.strip(), now),
            )
            self.conn.commit()
            return cur.lastrowid
        except:
            return None

    def get_standees(self):
        rows = self.conn.execute("SELECT * FROM standees ORDER BY id DESC").fetchall()
        return [{
            "id": r["id"], "name": r["name"], "total_units": r["total_units"],
            "storage_location": r["storage_location"], "created_at": r["created_at"],
        } for r in rows]

    def update_standee(self, standee_id, **kwargs):
        fields = []
        vals = []
        if "name" in kwargs: fields.append("name=?"); vals.append(kwargs["name"])
        if "total_units" in kwargs: fields.append("total_units=?"); vals.append(int(kwargs["total_units"]))
        if "storage_location" in kwargs: fields.append("storage_location=?"); vals.append(kwargs["storage_location"])
        if fields:
            vals.append(int(standee_id))
            self.conn.execute(f"UPDATE standees SET {', '.join(fields)} WHERE id=?", vals)
            self.conn.commit()

    def delete_standee(self, standee_id):
        self.conn.execute("DELETE FROM standee_assignments WHERE standee_id=?", (int(standee_id),))
        self.conn.execute("DELETE FROM standees WHERE id=?", (int(standee_id),))
        self.conn.commit()

    def assign_standee(self, standee_id, apartment_id, assigned_to, start_date, end_date, quantity, notes=""):
        now = _now_ist()
        cur = self.conn.execute(
            "INSERT INTO standee_assignments (standee_id, apartment_id, assigned_to, start_date, end_date, quantity, notes, status, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, 'Pending', ?)",
            (int(standee_id), int(apartment_id), assigned_to, start_date, end_date,
             int(quantity) if quantity else 0, notes or "", now),
        )
        self.conn.commit()
        return cur.lastrowid

    def get_assignments(self, apartment_id=None, assigned_to=None):
        sql = """SELECT sa.*, s.name as standee_name, a.apartment_name
                 FROM standee_assignments sa
                 JOIN standees s ON sa.standee_id = s.id
                 JOIN apartments a ON sa.apartment_id = a.id"""
        params = []
        where = []
        if apartment_id:
            where.append("sa.apartment_id=?")
            params.append(int(apartment_id))
        if assigned_to:
            where.append("sa.assigned_to=?")
            params.append(assigned_to)
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY sa.id DESC"
        rows = self.conn.execute(sql, params).fetchall()
        return [{
            "id": r["id"], "standee_id": r["standee_id"], "apartment_id": r["apartment_id"],
            "assigned_to": r["assigned_to"],
            "start_date": r["start_date"], "end_date": r["end_date"],
            "quantity": r["quantity"], "notes": r["notes"],
            "status": r["status"], "placed_at": r["placed_at"], "removed_at": r["removed_at"],
            "standee_name": r["standee_name"], "apartment_name": r["apartment_name"],
            "created_at": r["created_at"],
        } for r in rows]

    def update_assignment_status(self, assignment_id, status):
        now = _now_ist()
        if status == "Placed":
            self.conn.execute("UPDATE standee_assignments SET status=?, placed_at=? WHERE id=?",
                              (status, now, int(assignment_id)))
        elif status == "Removed":
            self.conn.execute("UPDATE standee_assignments SET status=?, removed_at=? WHERE id=?",
                              (status, now, int(assignment_id)))
        else:
            self.conn.execute("UPDATE standee_assignments SET status=? WHERE id=?",
                              (status, int(assignment_id)))
        self.conn.commit()

    def update_assignment(self, assignment_id, **kwargs):
        fields = []
        vals = []
        for k in ("standee_id", "apartment_id", "assigned_to", "start_date", "end_date", "quantity", "notes"):
            if k in kwargs and kwargs[k] is not None:
                fields.append(f"{k}=?")
                vals.append(kwargs[k])
        if fields:
            vals.append(int(assignment_id))
            self.conn.execute(f"UPDATE standee_assignments SET {', '.join(fields)} WHERE id=?", vals)
            self.conn.commit()

    def get_standee_tasks_for_user(self, username, date):
        rows = self.conn.execute(
            """SELECT sa.*, s.name AS standee_name, a.apartment_name
               FROM standee_assignments sa
               LEFT JOIN standees s ON s.id=sa.standee_id
               LEFT JOIN apartments a ON a.id=sa.apartment_id
               WHERE sa.assigned_to=? AND (sa.start_date=? OR sa.end_date=?)
               ORDER BY sa.id DESC""",
            (username, date, date),
        ).fetchall()
        out = []
        for r in rows:
            is_place = r["start_date"] == date and r["status"] != "Placed" and r["status"] != "Removed"
            is_remove = r["end_date"] == date and r["status"] == "Placed"
            task_type = "place" if is_place else ("remove" if is_remove else r["status"].lower())
            out.append({
                "id": r["id"],
                "standee_name": r["standee_name"] or "",
                "apartment_name": r["apartment_name"] or "",
                "quantity": r["quantity"],
                "task_type": task_type,
                "status": r["status"],
                "start_date": r["start_date"],
                "end_date": r["end_date"],
                "notes": r["notes"] or "",
            })
        return out

    def get_standee_usage(self, standee_id):
        row = self.conn.execute(
            "SELECT COALESCE(SUM(quantity),0) FROM standee_assignments WHERE standee_id=?",
            (int(standee_id),),
        ).fetchone()
        return row[0] if row else 0

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
            """SELECT assigned_date FROM apartments
               WHERE assigned_to=? AND assigned_date!=''
               GROUP BY assigned_date
               HAVING COUNT(*)>COUNT(CASE WHEN status='Visited' THEN 1 END)
               ORDER BY assigned_date""",
            (username,),
        ).fetchall()
        return [r["assigned_date"] for r in rows]

    # ── helpers ──
    def _apt_row(self, r):
        try:
            notes = r["notes_for_field"] or ""
        except (KeyError, IndexError):
            notes = ""
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
            "Notes for Field": notes,
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
        self.url = "https://ppxyhlmlymvhrjdcnoks.supabase.co"
        self.key = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InBweHlobG1seW12aHJqZGNub2tzIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc4MjM2MzY1NCwiZXhwIjoyMDk3OTM5NjU0fQ.D7QZbfzpZKtutgo4lp4F8R15HNlzQAf7N3ApBz6GQ6s"
        self.supabase = create_client(self.url, self.key)
        self._run_migration()

    def _run_migration(self):
        """Add notes_for_field column if missing."""
        try:
            payload = {"query": "ALTER TABLE apartments ADD COLUMN IF NOT EXISTS notes_for_field TEXT DEFAULT ''"}
            headers = {"apikey": self.key, "Authorization": f"Bearer {self.key}", "Content-Type": "application/json"}
            resp = requests.post(f"{self.url}/rest/v1/rpc/pg_query", json=payload, headers=headers, timeout=10)
        except:
            pass

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
            "notes_for_field": "",
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
        result = self.supabase.table("apartments").select("*").neq("status", "Deleted").order("id", desc=True).execute()
        return self._apt_rows(result.data)

    def assign_apartments(self, apartment_ids, assigned_to, assigned_date, notes_for_field=""):
        for aid in (int(x) for x in apartment_ids):
            self.supabase.table("apartments").update({
                "assigned_to": assigned_to,
                "assigned_date": assigned_date,
                "notes_for_field": notes_for_field,
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
            "Created By": "created_by",
            "Created At": "created_at",
            "Notes for Field": "notes_for_field",
        }
        updates = {mapping[k]: v for k, v in kwargs.items() if k in mapping}
        if updates:
            self.supabase.table("apartments").update(updates).eq("id", int(apartment_id)).execute()

    def delete_apartment(self, apartment_id):
        self.supabase.table("apartments").update({"status": "Deleted"}).eq("id", int(apartment_id)).execute()

    def restore_apartment(self, apartment_id):
        self.supabase.table("apartments").update({"status": "Pending"}).eq("id", int(apartment_id)).execute()

    def get_deleted_apartments(self):
        result = self.supabase.table("apartments").select("*").eq("status", "Deleted").order("id", desc=True).execute()
        return self._apt_rows(result.data)

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
        result = self.supabase.table("apartments").select("assigned_date,status").eq("assigned_to", username).neq("assigned_date", "").execute()
        date_status = {}
        for r in result.data:
            d = r.get("assigned_date")
            if d:
                date_status.setdefault(d, {"total": 0, "visited": 0})
                date_status[d]["total"] += 1
                if r.get("status") == "Visited":
                    date_status[d]["visited"] += 1
        return sorted(d for d, s in date_status.items() if s["total"] > s["visited"])

    # ── helpers ──
    def _standee_rows(self, data):
        return [{
            "id": r["id"], "name": r["name"],
            "total_units": r["total_units"],
            "storage_location": r.get("storage_location", ""),
            "created_at": r["created_at"],
        } for r in data]

    def _assignment_rows(self, data):
        return [{
            "id": r["id"], "standee_id": r["standee_id"],
            "apartment_id": r["apartment_id"],
            "start_date": r["start_date"], "end_date": r["end_date"],
            "quantity": r["quantity"], "notes": r.get("notes", ""),
            "standee_name": r.get("standee_name", ""),
            "apartment_name": r.get("apartment_name", ""),
            "created_at": r.get("created_at", ""),
        } for r in data]

    # ── Standees (Supabase) ──
    def add_standee(self, name, total_units, storage_location):
        data = {
            "name": name.strip(),
            "total_units": int(total_units) if total_units else 0,
            "storage_location": storage_location.strip(),
            "created_at": _now_ist(),
        }
        try:
            result = self.supabase.table("standees").insert(data).execute()
            return result.data[0]["id"] if result.data else None
        except:
            return None

    def get_standees(self):
        result = self.supabase.table("standees").select("*").order("id", desc=True).execute()
        return self._standee_rows(result.data)

    def update_standee(self, standee_id, **kwargs):
        updates = {}
        if "name" in kwargs: updates["name"] = kwargs["name"]
        if "total_units" in kwargs: updates["total_units"] = int(kwargs["total_units"])
        if "storage_location" in kwargs: updates["storage_location"] = kwargs["storage_location"]
        if updates:
            self.supabase.table("standees").update(updates).eq("id", int(standee_id)).execute()

    def delete_standee(self, standee_id):
        self.supabase.table("standee_assignments").delete().eq("standee_id", int(standee_id)).execute()
        self.supabase.table("standees").delete().eq("id", int(standee_id)).execute()

    def assign_standee(self, standee_id, apartment_id, assigned_to, start_date, end_date, quantity, notes=""):
        data = {
            "standee_id": int(standee_id),
            "apartment_id": int(apartment_id),
            "assigned_to": assigned_to,
            "start_date": start_date,
            "end_date": end_date,
            "quantity": int(quantity) if quantity else 0,
            "notes": notes or "",
            "status": "Pending",
            "created_at": _now_ist(),
        }
        result = self.supabase.table("standee_assignments").insert(data).execute()
        return result.data[0]["id"] if result.data else None

    def get_assignments(self, apartment_id=None, assigned_to=None):
        query = self.supabase.table("standee_assignments").select(
            "*, standees!inner(name), apartments!inner(apartment_name)"
        ).order("id", desc=True)
        if apartment_id:
            query = query.eq("apartment_id", int(apartment_id))
        if assigned_to:
            query = query.eq("assigned_to", assigned_to)
        result = query.execute()
        rows = []
        for r in result.data:
            rows.append({
                "id": r["id"], "standee_id": r["standee_id"],
                "apartment_id": r["apartment_id"],
                "assigned_to": r.get("assigned_to", ""),
                "start_date": r["start_date"], "end_date": r["end_date"],
                "quantity": r["quantity"], "notes": r.get("notes", ""),
                "status": r.get("status", "Pending"),
                "placed_at": r.get("placed_at", ""),
                "removed_at": r.get("removed_at", ""),
                "standee_name": r["standees"]["name"] if r.get("standees") else "",
                "apartment_name": r["apartments"]["apartment_name"] if r.get("apartments") else "",
                "created_at": r.get("created_at", ""),
            })
        return rows

    def get_standee_tasks_for_user(self, username, date):
        result = self.supabase.table("standee_assignments").select(
            "*, standees!inner(name), apartments!inner(apartment_name)"
        ).eq("assigned_to", username).or_(
            f"start_date.eq.{date},end_date.eq.{date}"
        ).order("id", desc=True).execute()
        out = []
        for r in result.data:
            is_place = r["start_date"] == date and r.get("status") not in ("Placed", "Removed")
            is_remove = r["end_date"] == date and r.get("status") == "Placed"
            task_type = "place" if is_place else ("remove" if is_remove else r.get("status", "pending").lower())
            out.append({
                "id": r["id"],
                "standee_name": r["standees"]["name"] if r.get("standees") else "",
                "apartment_name": r["apartments"]["apartment_name"] if r.get("apartments") else "",
                "quantity": r["quantity"],
                "task_type": task_type,
                "status": r.get("status", "Pending"),
                "start_date": r["start_date"],
                "end_date": r["end_date"],
                "notes": r.get("notes", ""),
            })
        return out

    def update_assignment_status(self, assignment_id, status):
        now = _now_ist()
        updates = {"status": status}
        if status == "Placed":
            updates["placed_at"] = now
        elif status == "Removed":
            updates["removed_at"] = now
        self.supabase.table("standee_assignments").update(updates).eq("id", int(assignment_id)).execute()

    def update_assignment(self, assignment_id, **kwargs):
        updates = {}
        for k in ("standee_id", "apartment_id", "assigned_to", "start_date", "end_date", "quantity", "notes"):
            if k in kwargs and kwargs[k] is not None:
                updates[k] = kwargs[k]
        if updates:
            self.supabase.table("standee_assignments").update(updates).eq("id", int(assignment_id)).execute()

    def get_standee_usage(self, standee_id):
        result = self.supabase.table("standee_assignments").select("quantity").eq("standee_id", int(standee_id)).execute()
        return sum(r.get("quantity", 0) or 0 for r in result.data)

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
            "Notes for Field": r.get("notes_for_field", ""),
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
