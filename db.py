"""Data layer.

Local development uses SQLite (``local_dev.db``).
Production uses Supabase — enabled when ``DATABASE_BACKEND=supabase`` or ``RENDER`` is
set, and both ``SUPABASE_URL`` and ``SUPABASE_KEY`` are present in the environment.

Both backends expose the same method surface; the rest of the app never checks which
one is active.  ``get_db()`` returns the singleton.
"""

import json
import os
import sqlite3
from datetime import datetime, timezone, timedelta

from config import STATUS_PENDING, STATUS_COLLECTED, STATUS_NO_NUMBER

IST = timezone(timedelta(hours=5, minutes=30))


def _now():
    return datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S")


def _status_for(outcome):
    return STATUS_COLLECTED if outcome == "number" else STATUS_NO_NUMBER


# ═══════════════════════════════════════════════════════════════════════════
#  SQLite backend
# ═══════════════════════════════════════════════════════════════════════════
class SQLiteDatabase:
    def __init__(self, path="local_dev.db"):
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA foreign_keys=ON")
        self._create()

    def _create(self):
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                name TEXT NOT NULL DEFAULT '',
                password_hash TEXT NOT NULL,
                workspace TEXT NOT NULL DEFAULT 'btl',
                active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL DEFAULT ''
            );

            CREATE TABLE IF NOT EXISTS apartments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                hub TEXT NOT NULL DEFAULT '',
                location_link TEXT NOT NULL DEFAULT '',
                assigned_to TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'Pending',
                deleted INTEGER NOT NULL DEFAULT 0,
                created_by TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT ''
            );

            CREATE TABLE IF NOT EXISTS collections (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                apartment_id INTEGER NOT NULL UNIQUE REFERENCES apartments(id) ON DELETE CASCADE,
                outcome TEXT NOT NULL DEFAULT 'number',       -- 'number' | 'no_number'
                phone TEXT NOT NULL DEFAULT '',
                designation TEXT NOT NULL DEFAULT '',
                no_number_reason TEXT NOT NULL DEFAULT '',
                collected_by TEXT NOT NULL DEFAULT '',
                collected_at TEXT NOT NULL DEFAULT '',
                updated_at TEXT NOT NULL DEFAULT ''
            );

            CREATE TABLE IF NOT EXISTS collection_campaigns (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                collection_id INTEGER NOT NULL REFERENCES collections(id) ON DELETE CASCADE,
                campaign TEXT NOT NULL,
                price REAL NOT NULL DEFAULT 0,
                days INTEGER NOT NULL DEFAULT 0
            );
            """
        )
        self.conn.commit()

    # ── users ──────────────────────────────────────────────────────────────
    def count_users(self):
        return self.conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]

    def get_user(self, username):
        r = self.conn.execute(
            "SELECT * FROM users WHERE username=?", (username,)
        ).fetchone()
        return dict(r) if r else None

    def get_user_by_id(self, user_id):
        r = self.conn.execute("SELECT * FROM users WHERE id=?", (int(user_id),)).fetchone()
        return dict(r) if r else None

    def list_users(self):
        rows = self.conn.execute(
            "SELECT * FROM users ORDER BY workspace, username"
        ).fetchall()
        return [dict(r) for r in rows]

    def btl_users(self):
        rows = self.conn.execute(
            "SELECT username, name FROM users WHERE workspace='btl' AND active=1 ORDER BY name"
        ).fetchall()
        return [dict(r) for r in rows]

    def create_user(self, username, name, password_hash, workspace):
        try:
            cur = self.conn.execute(
                "INSERT INTO users (username, name, password_hash, workspace, active, created_at) "
                "VALUES (?, ?, ?, ?, 1, ?)",
                (username, name, password_hash, workspace, _now()),
            )
            self.conn.commit()
            return cur.lastrowid
        except sqlite3.IntegrityError:
            return None

    def set_user_active(self, user_id, active):
        self.conn.execute(
            "UPDATE users SET active=? WHERE id=?", (1 if active else 0, int(user_id))
        )
        self.conn.commit()

    def set_user_password(self, user_id, password_hash):
        self.conn.execute(
            "UPDATE users SET password_hash=? WHERE id=?", (password_hash, int(user_id))
        )
        self.conn.commit()

    # ── apartments ───────────────────────────────────────────────────────
    def add_apartment(self, name, hub, location_link, created_by):
        cur = self.conn.execute(
            "INSERT INTO apartments (name, hub, location_link, created_by, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (name, hub, location_link, created_by, _now()),
        )
        self.conn.commit()
        return cur.lastrowid

    def bulk_add_apartments(self, rows, created_by):
        now = _now()
        self.conn.executemany(
            "INSERT INTO apartments (name, hub, location_link, created_by, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            [(n, h, l, created_by, now) for (n, h, l) in rows],
        )
        self.conn.commit()
        return len(rows)

    def list_apartments(self, include_deleted=False):
        sql = "SELECT * FROM apartments"
        if not include_deleted:
            sql += " WHERE deleted=0"
        sql += " ORDER BY id DESC"
        return [dict(r) for r in self.conn.execute(sql).fetchall()]

    def list_deleted_apartments(self):
        rows = self.conn.execute(
            "SELECT * FROM apartments WHERE deleted=1 ORDER BY id DESC"
        ).fetchall()
        return [dict(r) for r in rows]

    def list_apartments_for_btl(self, username):
        rows = self.conn.execute(
            "SELECT * FROM apartments WHERE deleted=0 AND assigned_to=? ORDER BY id DESC",
            (username,),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_apartment(self, apt_id):
        r = self.conn.execute(
            "SELECT * FROM apartments WHERE id=?", (int(apt_id),)
        ).fetchone()
        return dict(r) if r else None

    def update_apartment(self, apt_id, name=None, hub=None, location_link=None):
        sets, vals = [], []
        for col, val in (("name", name), ("hub", hub), ("location_link", location_link)):
            if val is not None:
                sets.append(f"{col}=?")
                vals.append(val)
        if not sets:
            return
        vals.append(int(apt_id))
        self.conn.execute(f"UPDATE apartments SET {', '.join(sets)} WHERE id=?", vals)
        self.conn.commit()

    def assign_apartments(self, apt_ids, assigned_to):
        ids = [int(x) for x in apt_ids]
        self.conn.executemany(
            "UPDATE apartments SET assigned_to=?, status=? WHERE id=?",
            [(assigned_to, STATUS_PENDING, i) for i in ids],
        )
        self.conn.commit()

    def soft_delete_apartment(self, apt_id):
        self.conn.execute(
            "UPDATE apartments SET deleted=1 WHERE id=?", (int(apt_id),)
        )
        self.conn.commit()

    def restore_apartment(self, apt_id):
        self.conn.execute(
            "UPDATE apartments SET deleted=0 WHERE id=?", (int(apt_id),)
        )
        self.conn.commit()

    # ── collections ──────────────────────────────────────────────────────
    def _campaigns_for(self, collection_id):
        rows = self.conn.execute(
            "SELECT campaign, price, days FROM collection_campaigns WHERE collection_id=? ORDER BY id",
            (int(collection_id),),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_collection(self, apartment_id):
        r = self.conn.execute(
            "SELECT * FROM collections WHERE apartment_id=?", (int(apartment_id),)
        ).fetchone()
        if not r:
            return None
        d = dict(r)
        d["campaigns"] = self._campaigns_for(d["id"])
        return d

    def collections_by_apartment(self):
        """{apartment_id: {...collection, campaign_count}} for list/export views."""
        rows = self.conn.execute("SELECT * FROM collections").fetchall()
        counts = {
            r["collection_id"]: r["c"]
            for r in self.conn.execute(
                "SELECT collection_id, COUNT(*) AS c FROM collection_campaigns GROUP BY collection_id"
            ).fetchall()
        }
        out = {}
        for r in rows:
            d = dict(r)
            d["campaign_count"] = counts.get(d["id"], 0)
            out[d["apartment_id"]] = d
        return out

    def save_collection(self, apartment_id, outcome, phone, designation,
                        no_number_reason, campaigns, collected_by):
        apartment_id = int(apartment_id)
        now = _now()
        existing = self.conn.execute(
            "SELECT id, collected_at FROM collections WHERE apartment_id=?", (apartment_id,)
        ).fetchone()
        if existing:
            cid = existing["id"]
            self.conn.execute(
                "UPDATE collections SET outcome=?, phone=?, designation=?, no_number_reason=?, "
                "collected_by=?, updated_at=? WHERE id=?",
                (outcome, phone, designation, no_number_reason, collected_by, now, cid),
            )
        else:
            cur = self.conn.execute(
                "INSERT INTO collections (apartment_id, outcome, phone, designation, "
                "no_number_reason, collected_by, collected_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (apartment_id, outcome, phone, designation, no_number_reason,
                 collected_by, now, now),
            )
            cid = cur.lastrowid

        self.conn.execute("DELETE FROM collection_campaigns WHERE collection_id=?", (cid,))
        if outcome == "number" and campaigns:
            self.conn.executemany(
                "INSERT INTO collection_campaigns (collection_id, campaign, price, days) "
                "VALUES (?, ?, ?, ?)",
                [(cid, c["campaign"], float(c["price"] or 0), int(c["days"] or 0))
                 for c in campaigns],
            )

        self.conn.execute(
            "UPDATE apartments SET status=? WHERE id=?",
            (_status_for(outcome), apartment_id),
        )
        self.conn.commit()
        return cid


# ═══════════════════════════════════════════════════════════════════════════
#  Supabase backend (production)
# ═══════════════════════════════════════════════════════════════════════════
class SupabaseDatabase:
    def __init__(self, url, key):
        from supabase import create_client

        self.sb = create_client(url, key)

    # ── users ──
    def count_users(self):
        r = self.sb.table("users").select("id", count="exact").limit(1).execute()
        return r.count or 0

    def get_user(self, username):
        r = self.sb.table("users").select("*").eq("username", username).limit(1).execute()
        return r.data[0] if r.data else None

    def get_user_by_id(self, user_id):
        r = self.sb.table("users").select("*").eq("id", int(user_id)).limit(1).execute()
        return r.data[0] if r.data else None

    def list_users(self):
        return (
            self.sb.table("users").select("*").order("workspace").order("username").execute().data
        )

    def btl_users(self):
        return (
            self.sb.table("users")
            .select("username,name")
            .eq("workspace", "btl")
            .eq("active", True)
            .order("name")
            .execute()
            .data
        )

    def create_user(self, username, name, password_hash, workspace):
        try:
            r = self.sb.table("users").insert({
                "username": username, "name": name, "password_hash": password_hash,
                "workspace": workspace, "active": True, "created_at": _now(),
            }).execute()
            return r.data[0]["id"] if r.data else None
        except Exception:
            return None

    def set_user_active(self, user_id, active):
        self.sb.table("users").update({"active": bool(active)}).eq("id", int(user_id)).execute()

    def set_user_password(self, user_id, password_hash):
        self.sb.table("users").update({"password_hash": password_hash}).eq("id", int(user_id)).execute()

    # ── apartments ──
    def add_apartment(self, name, hub, location_link, created_by):
        r = self.sb.table("apartments").insert({
            "name": name, "hub": hub, "location_link": location_link,
            "assigned_to": "", "status": STATUS_PENDING, "deleted": False,
            "created_by": created_by, "created_at": _now(),
        }).execute()
        return r.data[0]["id"] if r.data else None

    def bulk_add_apartments(self, rows, created_by):
        now = _now()
        payload = [{
            "name": n, "hub": h, "location_link": l, "assigned_to": "",
            "status": STATUS_PENDING, "deleted": False,
            "created_by": created_by, "created_at": now,
        } for (n, h, l) in rows]
        if payload:
            self.sb.table("apartments").insert(payload).execute()
        return len(payload)

    def list_apartments(self, include_deleted=False):
        q = self.sb.table("apartments").select("*").order("id", desc=True)
        if not include_deleted:
            q = q.eq("deleted", False)
        return q.execute().data

    def list_deleted_apartments(self):
        return (
            self.sb.table("apartments").select("*").eq("deleted", True)
            .order("id", desc=True).execute().data
        )

    def list_apartments_for_btl(self, username):
        return (
            self.sb.table("apartments").select("*")
            .eq("deleted", False).eq("assigned_to", username)
            .order("id", desc=True).execute().data
        )

    def get_apartment(self, apt_id):
        r = self.sb.table("apartments").select("*").eq("id", int(apt_id)).limit(1).execute()
        return r.data[0] if r.data else None

    def update_apartment(self, apt_id, name=None, hub=None, location_link=None):
        upd = {}
        if name is not None:
            upd["name"] = name
        if hub is not None:
            upd["hub"] = hub
        if location_link is not None:
            upd["location_link"] = location_link
        if upd:
            self.sb.table("apartments").update(upd).eq("id", int(apt_id)).execute()

    def assign_apartments(self, apt_ids, assigned_to):
        for i in (int(x) for x in apt_ids):
            self.sb.table("apartments").update(
                {"assigned_to": assigned_to, "status": STATUS_PENDING}
            ).eq("id", i).execute()

    def soft_delete_apartment(self, apt_id):
        self.sb.table("apartments").update({"deleted": True}).eq("id", int(apt_id)).execute()

    def restore_apartment(self, apt_id):
        self.sb.table("apartments").update({"deleted": False}).eq("id", int(apt_id)).execute()

    # ── collections ──
    def get_collection(self, apartment_id):
        r = self.sb.table("collections").select("*").eq("apartment_id", int(apartment_id)).limit(1).execute()
        if not r.data:
            return None
        d = r.data[0]
        d["campaigns"] = (
            self.sb.table("collection_campaigns").select("campaign,price,days")
            .eq("collection_id", d["id"]).order("id").execute().data
        )
        return d

    def collections_by_apartment(self):
        rows = self.sb.table("collections").select("*").execute().data
        camp = self.sb.table("collection_campaigns").select("collection_id").execute().data
        counts = {}
        for c in camp:
            counts[c["collection_id"]] = counts.get(c["collection_id"], 0) + 1
        out = {}
        for d in rows:
            d["campaign_count"] = counts.get(d["id"], 0)
            out[d["apartment_id"]] = d
        return out

    def save_collection(self, apartment_id, outcome, phone, designation,
                        no_number_reason, campaigns, collected_by):
        apartment_id = int(apartment_id)
        now = _now()
        existing = self.sb.table("collections").select("id").eq("apartment_id", apartment_id).limit(1).execute()
        row = {
            "outcome": outcome, "phone": phone, "designation": designation,
            "no_number_reason": no_number_reason, "collected_by": collected_by,
            "updated_at": now,
        }
        if existing.data:
            cid = existing.data[0]["id"]
            self.sb.table("collections").update(row).eq("id", cid).execute()
        else:
            row.update({"apartment_id": apartment_id, "collected_at": now})
            cid = self.sb.table("collections").insert(row).execute().data[0]["id"]

        self.sb.table("collection_campaigns").delete().eq("collection_id", cid).execute()
        if outcome == "number" and campaigns:
            self.sb.table("collection_campaigns").insert([
                {"collection_id": cid, "campaign": c["campaign"],
                 "price": float(c["price"] or 0), "days": int(c["days"] or 0)}
                for c in campaigns
            ]).execute()

        self.sb.table("apartments").update({"status": _status_for(outcome)}).eq("id", apartment_id).execute()
        return cid


# ═══════════════════════════════════════════════════════════════════════════
#  Factory
# ═══════════════════════════════════════════════════════════════════════════
_db = None


def _use_supabase():
    if os.environ.get("DATABASE_BACKEND", "").lower() == "supabase":
        return True
    return bool(os.environ.get("RENDER"))


def get_db():
    global _db
    if _db is None:
        if _use_supabase():
            url = os.environ.get("SUPABASE_URL")
            key = os.environ.get("SUPABASE_KEY")
            if not (url and key):
                raise RuntimeError(
                    "Supabase backend selected but SUPABASE_URL / SUPABASE_KEY are not set"
                )
            _db = SupabaseDatabase(url, key)
        else:
            _db = SQLiteDatabase()
    return _db
