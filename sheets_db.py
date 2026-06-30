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
                created_at TEXT DEFAULT '',
                damage_reported INTEGER DEFAULT 0,
                damage_details TEXT DEFAULT '',
                return_location TEXT DEFAULT '',
                collection_location TEXT DEFAULT ''
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
        try:
            self.conn.execute("ALTER TABLE standee_assignments ADD COLUMN damage_reported INTEGER DEFAULT 0")
        except:
            pass
        try:
            self.conn.execute("ALTER TABLE standee_assignments ADD COLUMN damage_details TEXT DEFAULT ''")
        except:
            pass
        try:
            self.conn.execute("ALTER TABLE standee_assignments ADD COLUMN return_location TEXT DEFAULT ''")
        except:
            pass
        try:
            self.conn.execute("ALTER TABLE standee_assignments ADD COLUMN collection_location TEXT DEFAULT ''")
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

    def get_active_placements(self):
        """Return apartments where standees are currently Placed (for pickup source)."""
        rows = self.conn.execute(
            """SELECT DISTINCT a.id, a.apartment_name, a.hub_name, sa.standee_id, s.name AS standee_name, sa.quantity
               FROM standee_assignments sa
               JOIN apartments a ON a.id=sa.apartment_id
               JOIN standees s ON s.id=sa.standee_id
               WHERE sa.status='Placed'
               ORDER BY a.apartment_name"""
        ).fetchall()
        return [{
            "apartment_id": r["id"],
            "apartment_name": r["apartment_name"],
            "hub_name": r["hub_name"],
            "standee_id": r["standee_id"],
            "standee_name": r["standee_name"],
            "quantity": r["quantity"],
        } for r in rows]

    def assign_standee(self, standee_id, apartment_id, assigned_to, start_date, end_date, quantity, notes="", collection_location=""):
        now = _now_ist()
        cur = self.conn.execute(
            "INSERT INTO standee_assignments (standee_id, apartment_id, assigned_to, start_date, end_date, quantity, notes, collection_location, status, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'Pending', ?)",
            (int(standee_id), int(apartment_id), assigned_to, start_date, end_date,
             int(quantity) if quantity else 0, notes or "", collection_location, now),
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
        def _g(row, key, default=""):
            try:
                v = row[key]
                return v if v is not None else default
            except (KeyError, IndexError):
                return default
        return [{
            "id": r["id"], "standee_id": r["standee_id"], "apartment_id": r["apartment_id"],
            "assigned_to": r["assigned_to"],
            "start_date": r["start_date"], "end_date": r["end_date"],
            "quantity": r["quantity"], "notes": _g(r, "notes", ""),
            "status": r["status"], "placed_at": _g(r, "placed_at", ""), "removed_at": _g(r, "removed_at", ""),
            "standee_name": r["standee_name"], "apartment_name": r["apartment_name"],
            "created_at": _g(r, "created_at", ""),
            "damage_reported": int(_g(r, "damage_reported", 0)),
            "damage_details": _g(r, "damage_details", ""),
            "return_location": _g(r, "return_location", ""),
            "collection_location": _g(r, "collection_location", ""),
        } for r in rows]

    def update_assignment_status(self, assignment_id, status, **kwargs):
        now = _now_ist()
        extra = ""
        vals = []
        if kwargs.get("damage_reported"):
            extra += ", damage_reported=?, damage_details=?"
            vals += [int(kwargs["damage_reported"]), kwargs.get("damage_details", "")]
        if kwargs.get("collection_location"):
            extra += ", collection_location=?"
            vals.append(kwargs["collection_location"])
        if kwargs.get("return_location"):
            extra += ", return_location=?"
            vals.append(kwargs["return_location"])
        if status == "Placed":
            self.conn.execute(
                f"UPDATE standee_assignments SET status=?, placed_at=?{extra} WHERE id=?",
                [status, now] + vals + [int(assignment_id)],
            )
        elif status == "Removed":
            self.conn.execute(
                f"UPDATE standee_assignments SET status=?, removed_at=?{extra} WHERE id=?",
                [status, now] + vals + [int(assignment_id)],
            )
        else:
            self.conn.execute(
                f"UPDATE standee_assignments SET status=?{extra} WHERE id=?",
                [status] + vals + [int(assignment_id)],
            )
        self.conn.commit()

    def update_assignment(self, assignment_id, **kwargs):
        fields = []
        vals = []
        for k in ("standee_id", "apartment_id", "assigned_to", "start_date", "end_date", "quantity", "notes", "collection_location"):
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
            # Skip fully completed tasks (removed, or already placed on start date)
            if r["status"] == "Removed":
                continue
            if r["start_date"] == date and r["status"] == "Placed":
                continue
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
                "collection_location": r["collection_location"] if r["collection_location"] else "",
            })
        return out

    def get_standee_usage(self, standee_id):
        row = self.conn.execute(
            "SELECT COALESCE(SUM(quantity),0) FROM standee_assignments WHERE standee_id=? AND status='Placed'",
            (int(standee_id),),
        ).fetchone()
        return row[0] if row else 0

    def get_standee_available_dates_for_user(self, username):
        """Return dates where user has pending standee tasks (sorted, unique)."""
        rows = self.conn.execute(
            """SELECT DISTINCT sa.start_date AS d FROM standee_assignments sa
               WHERE sa.assigned_to=? AND sa.start_date!='' AND sa.status!='Placed' AND sa.status!='Removed'
               UNION
               SELECT DISTINCT sa.end_date FROM standee_assignments sa
               WHERE sa.assigned_to=? AND sa.end_date!='' AND sa.status='Placed'
               ORDER BY d""",
            (username, username),
        ).fetchall()
        return [r["d"] for r in rows]

    def get_standee_detail(self, standee_id):
        """Return standee info + all assignment history + current active location."""
        s = self.conn.execute("SELECT * FROM standees WHERE id=?", (int(standee_id),)).fetchone()
        if not s:
            return None
        def _g(row, key, default=""):
            try:
                v = row[key]
                return v if v is not None else default
            except (KeyError, IndexError):
                return default
        assignments = self.conn.execute(
            """SELECT sa.*, a.apartment_name
               FROM standee_assignments sa
               LEFT JOIN apartments a ON a.id=sa.apartment_id
               WHERE sa.standee_id=?
               ORDER BY sa.id DESC""",
            (int(standee_id),),
        ).fetchall()
        active = [a for a in assignments if a["status"] == "Placed"]
        current_location = active[0]["apartment_name"] if active else None
        current_assignment = dict(active[0]) if active else None
        return {
            "id": s["id"],
            "name": s["name"],
            "total_units": s["total_units"],
            "storage_location": _g(s, "storage_location", ""),
            "usage": self.get_standee_usage(standee_id),
            "available": s["total_units"] - self.get_standee_usage(standee_id),
            "current_location": current_location,
            "current_assignment": current_assignment,
            "history": [{
                "id": a["id"], "apartment_name": a["apartment_name"],
                "assigned_to": a["assigned_to"], "status": a["status"],
                "placed_at": a["placed_at"], "removed_at": a["removed_at"],
                "start_date": a["start_date"], "end_date": a["end_date"],
                "quantity": a["quantity"], "notes": a["notes"],
                "damage_reported": int(_g(a, "damage_reported", 0)),
                "damage_details": _g(a, "damage_details", ""),
                "return_location": _g(a, "return_location", ""),
            } for a in assignments],
        }

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
        try:
            result = self.supabase.table("apartments").insert(data).execute()
            return result.data[0]["id"] if result.data else None
        except Exception:
            # retry without notes_for_field (column may not exist yet)
            data.pop("notes_for_field", None)
            try:
                result = self.supabase.table("apartments").insert(data).execute()
                return result.data[0]["id"] if result.data else None
            except Exception:
                return None

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
        updates = {
            "assigned_to": assigned_to,
            "assigned_date": assigned_date,
            "status": "Pending",
        }
        updates["notes_for_field"] = notes_for_field
        for aid in (int(x) for x in apartment_ids):
            try:
                self.supabase.table("apartments").update(updates).eq("id", aid).execute()
            except Exception:
                # retry without notes_for_field
                minimal = {k: v for k, v in updates.items() if k != "notes_for_field"}
                try:
                    self.supabase.table("apartments").update(minimal).eq("id", aid).execute()
                except Exception:
                    pass

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
            try:
                self.supabase.table("apartments").update(updates).eq("id", int(apartment_id)).execute()
            except Exception:
                # retry without notes_for_field if it might not exist
                minimal = {k: v for k, v in updates.items() if k != "notes_for_field"}
                if minimal:
                    try:
                        self.supabase.table("apartments").update(minimal).eq("id", int(apartment_id)).execute()
                    except Exception:
                        pass

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

    def get_active_placements(self):
        """Return apartments where standees are currently Placed (for pickup source)."""
        try:
            result = self.supabase.table("standee_assignments").select(
                "*, apartments!inner(apartment_name, hub_name), standees!inner(name)"
            ).eq("status", "Placed").execute()
        except Exception:
            return []
        seen = {}
        out = []
        for r in (result.data or []):
            aid = r.get("apartment_id")
            if aid and aid not in seen:
                seen[aid] = True
                apt = r.get("apartments") or {}
                std = r.get("standees") or {}
                out.append({
                    "apartment_id": aid,
                    "apartment_name": apt.get("apartment_name", ""),
                    "hub_name": apt.get("hub_name", ""),
                    "standee_id": r.get("standee_id"),
                    "standee_name": std.get("name", ""),
                    "quantity": r.get("quantity", 0),
                })
        out.sort(key=lambda x: x["apartment_name"])
        return out

    def assign_standee(self, standee_id, apartment_id, assigned_to, start_date, end_date, quantity, notes="", collection_location=""):
        data = {
            "standee_id": int(standee_id),
            "apartment_id": int(apartment_id),
            "assigned_to": assigned_to,
            "start_date": start_date,
            "end_date": end_date,
            "quantity": int(quantity) if quantity else 0,
            "notes": notes or "",
            "collection_location": collection_location,
            "status": "Pending",
            "created_at": _now_ist(),
        }
        try:
            result = self.supabase.table("standee_assignments").insert(data).execute()
            return result.data[0]["id"] if result.data else None
        except Exception:
            # retry without status/collection_location/notes if columns don't exist yet
            minimal = {k: v for k, v in data.items() if k in ("standee_id", "apartment_id", "assigned_to", "start_date", "end_date", "quantity", "created_at")}
            try:
                result = self.supabase.table("standee_assignments").insert(minimal).execute()
                return result.data[0]["id"] if result.data else None
            except Exception:
                return None

    def get_assignments(self, apartment_id=None, assigned_to=None):
        query = self.supabase.table("standee_assignments").select(
            "*, standees!inner(name), apartments!inner(apartment_name)"
        ).order("id", desc=True)
        if apartment_id:
            query = query.eq("apartment_id", int(apartment_id))
        if assigned_to:
            query = query.eq("assigned_to", assigned_to)
        try:
            result = query.execute()
        except Exception:
            return []
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
                "damage_reported": r.get("damage_reported", 0) or 0,
                "damage_details": r.get("damage_details", "") or "",
                "return_location": r.get("return_location", "") or "",
                "collection_location": r.get("collection_location", "") or "",
            })
        return rows

    def get_standee_tasks_for_user(self, username, date):
        try:
            result = self.supabase.table("standee_assignments").select(
                "*, standees!inner(name), apartments!inner(apartment_name)"
            ).eq("assigned_to", username).or_(
                f"start_date.eq.{date},end_date.eq.{date}"
            ).order("id", desc=True).execute()
        except Exception:
            return []
        out = []
        for r in result.data:
            status = r.get("status", "Pending")
            # Skip fully completed tasks
            if status == "Removed":
                continue
            if r["start_date"] == date and status == "Placed":
                continue
            is_place = r["start_date"] == date and status not in ("Placed", "Removed")
            is_remove = r["end_date"] == date and status == "Placed"
            task_type = "place" if is_place else ("remove" if is_remove else status.lower())
            out.append({
                "id": r["id"],
                "standee_name": r["standees"]["name"] if r.get("standees") else "",
                "apartment_name": r["apartments"]["apartment_name"] if r.get("apartments") else "",
                "quantity": r["quantity"],
                "task_type": task_type,
                "status": status,
                "start_date": r["start_date"],
                "end_date": r["end_date"],
                "notes": r.get("notes", ""),
                "collection_location": r.get("collection_location", "") or "",
            })
        return out

    def update_assignment_status(self, assignment_id, status, **kwargs):
        now = _now_ist()
        updates = {"status": status}
        if status == "Placed":
            updates["placed_at"] = now
        elif status == "Removed":
            updates["removed_at"] = now
        if kwargs.get("damage_reported"):
            updates["damage_reported"] = int(kwargs["damage_reported"])
            updates["damage_details"] = kwargs.get("damage_details", "")
        if kwargs.get("collection_location"):
            updates["collection_location"] = kwargs["collection_location"]
        if kwargs.get("return_location"):
            updates["return_location"] = kwargs["return_location"]
        try:
            self.supabase.table("standee_assignments").update(updates).eq("id", int(assignment_id)).execute()
        except Exception:
            # fallback: skip columns that might not exist yet
            minimal = {k: v for k, v in updates.items() if k in ("placed_at", "removed_at")}
            if minimal:
                try:
                    self.supabase.table("standee_assignments").update(minimal).eq("id", int(assignment_id)).execute()
                except Exception:
                    pass

    def update_assignment(self, assignment_id, **kwargs):
        updates = {}
        for k in ("standee_id", "apartment_id", "assigned_to", "start_date", "end_date", "quantity", "notes", "collection_location"):
            if k in kwargs and kwargs[k] is not None:
                updates[k] = kwargs[k]
        if updates:
            self.supabase.table("standee_assignments").update(updates).eq("id", int(assignment_id)).execute()

    def get_standee_usage(self, standee_id):
        try:
            result = self.supabase.table("standee_assignments").select("quantity").eq("standee_id", int(standee_id)).eq("status", "Placed").execute()
        except Exception:
            return 0
        return sum(r.get("quantity", 0) or 0 for r in result.data)

    def get_standee_available_dates_for_user(self, username):
        """Return dates where user has pending standee tasks (sorted, unique)."""
        try:
            r_start = self.supabase.table("standee_assignments").select("start_date").eq("assigned_to", username).neq("status", "Placed").neq("status", "Removed").neq("start_date", "").execute()
            r_end = self.supabase.table("standee_assignments").select("end_date").eq("assigned_to", username).eq("status", "Placed").neq("end_date", "").execute()
        except Exception:
            return []
        seen = set()
        out = []
        for r in r_start.data:
            d = r["start_date"]
            if d and d not in seen:
                seen.add(d); out.append(d)
        for r in r_end.data:
            d = r["end_date"]
            if d and d not in seen:
                seen.add(d); out.append(d)
        out.sort()
        return out

    def get_standee_detail(self, standee_id):
        s_data = self.supabase.table("standees").select("*").eq("id", int(standee_id)).single().execute()
        s = s_data.data
        if not s:
            return None
        a_data = self.supabase.table("standee_assignments").select(
            "*, apartments!inner(apartment_name)"
        ).eq("standee_id", int(standee_id)).order("id", desc=True).execute()
        assignments = []
        active = []
        for r in a_data.data:
            row = {
                "id": r["id"], "apartment_name": r["apartments"]["apartment_name"],
                "assigned_to": r.get("assigned_to", ""), "status": r.get("status", ""),
                "placed_at": r.get("placed_at", ""), "removed_at": r.get("removed_at", ""),
                "start_date": r["start_date"], "end_date": r["end_date"],
                "quantity": r["quantity"], "notes": r.get("notes", ""),
                "damage_reported": r.get("damage_reported", 0) or 0,
                "damage_details": r.get("damage_details", "") or "",
                "collection_location": r.get("collection_location", "") or "",
                "return_location": r.get("return_location", "") or "",
            }
            assignments.append(row)
            if r.get("status") == "Placed":
                active.append(row)
        usage = self.get_standee_usage(standee_id)
        return {
            "id": s["id"], "name": s["name"],
            "total_units": s["total_units"],
            "storage_location": s.get("storage_location", ""),
            "usage": usage,
            "available": s["total_units"] - usage,
            "current_location": active[0]["apartment_name"] if active else None,
            "current_assignment": active[0] if active else None,
            "history": assignments,
        }

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
