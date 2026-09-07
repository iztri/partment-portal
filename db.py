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


def _prev_contact_shift(existing, new_phone):
    """(previous_contact_name, previous_phone, previous_saved_at) to write on a
    collection update: the old number moves to "previous" only when one existed
    and actually changed; otherwise the already-stored "previous" values stay."""
    existing = existing or {}
    old_phone = (existing.get("phone") or "").strip()
    if old_phone and old_phone != (new_phone or "").strip():
        return (
            existing.get("contact_name") or "",
            old_phone,
            existing.get("updated_at") or existing.get("collected_at") or _now(),
        )
    return (
        existing.get("previous_contact_name") or "",
        existing.get("previous_phone") or "",
        existing.get("previous_saved_at") or "",
    )


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
                is_admin INTEGER NOT NULL DEFAULT 0,
                active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL DEFAULT ''
            );

            CREATE TABLE IF NOT EXISTS user_permissions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL,
                feature TEXT NOT NULL,
                level TEXT NOT NULL DEFAULT 'edit',
                UNIQUE(username, feature)
            );

            CREATE TABLE IF NOT EXISTS hubs (
                hub_id INTEGER PRIMARY KEY,
                hub_name TEXT NOT NULL UNIQUE,
                created_at TEXT NOT NULL DEFAULT ''
            );

            CREATE TABLE IF NOT EXISTS apartments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                apartment_code TEXT NOT NULL DEFAULT '',
                hub TEXT NOT NULL DEFAULT '',
                location_link TEXT NOT NULL DEFAULT '',
                assigned_to TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'Pending',
                deleted INTEGER NOT NULL DEFAULT 0,
                recollect_at TEXT NOT NULL DEFAULT '',
                created_by TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT ''
            );

            CREATE TABLE IF NOT EXISTS collections (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                apartment_id INTEGER NOT NULL UNIQUE REFERENCES apartments(id) ON DELETE CASCADE,
                outcome TEXT NOT NULL DEFAULT 'number',       -- 'number' | 'no_number'
                contact_name TEXT NOT NULL DEFAULT '',
                phone TEXT NOT NULL DEFAULT '',
                designation TEXT NOT NULL DEFAULT '',
                total_units INTEGER NOT NULL DEFAULT 0,
                no_number_reason TEXT NOT NULL DEFAULT '',
                previous_contact_name TEXT NOT NULL DEFAULT '',
                previous_phone TEXT NOT NULL DEFAULT '',
                previous_saved_at TEXT NOT NULL DEFAULT '',
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

            CREATE TABLE IF NOT EXISTS standees (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                photo_path TEXT NOT NULL DEFAULT '',
                total_units INTEGER NOT NULL DEFAULT 0,
                storage_location TEXT NOT NULL DEFAULT '',
                active INTEGER NOT NULL DEFAULT 1,
                replaced_by INTEGER REFERENCES standees(id),
                damaged_resolved INTEGER NOT NULL DEFAULT 0,
                created_by TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT ''
            );

            CREATE TABLE IF NOT EXISTS standee_reprints (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                standee_id INTEGER NOT NULL REFERENCES standees(id) ON DELETE CASCADE,
                added_units INTEGER NOT NULL DEFAULT 0,
                note TEXT NOT NULL DEFAULT '',
                added_by TEXT NOT NULL DEFAULT '',
                added_at TEXT NOT NULL DEFAULT ''
            );

            CREATE TABLE IF NOT EXISTS standee_assignments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                standee_id INTEGER NOT NULL REFERENCES standees(id),
                apartment_id INTEGER NOT NULL REFERENCES apartments(id),
                assigned_to TEXT NOT NULL DEFAULT '',
                quantity INTEGER NOT NULL DEFAULT 0,
                duration_days INTEGER NOT NULL DEFAULT 0,
                collection_location TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'Assigned',
                placed_at TEXT NOT NULL DEFAULT '',
                placed_by TEXT NOT NULL DEFAULT '',
                collect_by TEXT NOT NULL DEFAULT '',
                collected_at TEXT NOT NULL DEFAULT '',
                collected_by TEXT NOT NULL DEFAULT '',
                quantity_returned INTEGER NOT NULL DEFAULT 0,
                quantity_damaged INTEGER NOT NULL DEFAULT 0,
                quantity_missing INTEGER NOT NULL DEFAULT 0,
                damage_note TEXT NOT NULL DEFAULT '',
                drop_location TEXT NOT NULL DEFAULT '',
                redeployed_to INTEGER,
                invoice_photo TEXT NOT NULL DEFAULT '',
                invoice_note TEXT NOT NULL DEFAULT '',
                created_by TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT '',
                updated_at TEXT NOT NULL DEFAULT ''
            );

            CREATE TABLE IF NOT EXISTS standee_photos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                assignment_id INTEGER NOT NULL REFERENCES standee_assignments(id) ON DELETE CASCADE,
                kind TEXT NOT NULL DEFAULT 'placement',
                path TEXT NOT NULL,
                uploaded_at TEXT NOT NULL DEFAULT ''
            );
            """
        )
        self.conn.commit()
        # migrate: add columns to pre-existing tables
        for stmt in (
            "ALTER TABLE collections ADD COLUMN contact_name TEXT NOT NULL DEFAULT ''",
            "ALTER TABLE collections ADD COLUMN total_units INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE standees ADD COLUMN active INTEGER NOT NULL DEFAULT 1",
            "ALTER TABLE standees ADD COLUMN replaced_by INTEGER REFERENCES standees(id)",
            "ALTER TABLE standees ADD COLUMN damaged_resolved INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE users ADD COLUMN is_admin INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE apartments ADD COLUMN apartment_code TEXT NOT NULL DEFAULT ''",
            "ALTER TABLE standee_assignments ADD COLUMN quantity_missing INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE standee_assignments ADD COLUMN redeployed_to INTEGER",
            "ALTER TABLE standee_assignments ADD COLUMN invoice_photo TEXT NOT NULL DEFAULT ''",
            "ALTER TABLE standee_assignments ADD COLUMN invoice_note TEXT NOT NULL DEFAULT ''",
            "ALTER TABLE standee_assignments ADD COLUMN updated_at TEXT NOT NULL DEFAULT ''",
            "ALTER TABLE apartments ADD COLUMN recollect_at TEXT NOT NULL DEFAULT ''",
            "ALTER TABLE collections ADD COLUMN previous_contact_name TEXT NOT NULL DEFAULT ''",
            "ALTER TABLE collections ADD COLUMN previous_phone TEXT NOT NULL DEFAULT ''",
            "ALTER TABLE collections ADD COLUMN previous_saved_at TEXT NOT NULL DEFAULT ''",
        ):
            try:
                self.conn.execute(stmt)
                self.conn.commit()
            except sqlite3.OperationalError:
                pass

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

    # ── admin + per-feature permissions ──────────────────────────────────
    def count_admins(self):
        return self.conn.execute(
            "SELECT COUNT(*) FROM users WHERE is_admin=1 AND active=1"
        ).fetchone()[0]

    def set_user_admin(self, user_id, is_admin):
        self.conn.execute(
            "UPDATE users SET is_admin=? WHERE id=?", (1 if is_admin else 0, int(user_id))
        )
        self.conn.commit()

    def promote_to_admin(self, username):
        self.conn.execute(
            "UPDATE users SET is_admin=1 WHERE username=?", (username,)
        )
        self.conn.commit()

    def list_permissions(self, username):
        rows = self.conn.execute(
            "SELECT feature, level FROM user_permissions WHERE username=?", (username,)
        ).fetchall()
        return {r["feature"]: r["level"] for r in rows}

    def get_permission(self, username, feature):
        r = self.conn.execute(
            "SELECT level FROM user_permissions WHERE username=? AND feature=?",
            (username, feature),
        ).fetchone()
        return r["level"] if r else None

    def set_permission(self, username, feature, level):
        cur = self.conn.execute(
            "UPDATE user_permissions SET level=? WHERE username=? AND feature=?",
            (level, username, feature),
        )
        if cur.rowcount == 0:
            self.conn.execute(
                "INSERT INTO user_permissions (username, feature, level) VALUES (?, ?, ?)",
                (username, feature, level),
            )
        self.conn.commit()

    def set_permissions(self, username, mapping):
        for feature, level in mapping.items():
            self.set_permission(username, feature, level)

    def clear_permissions(self, username):
        self.conn.execute(
            "DELETE FROM user_permissions WHERE username=?", (username,)
        )
        self.conn.commit()

    # ── hubs ─────────────────────────────────────────────────────────────
    def list_hubs(self):
        return [dict(r) for r in self.conn.execute(
            "SELECT hub_id, hub_name FROM hubs ORDER BY hub_name"
        ).fetchall()]

    def hub_names(self):
        return [r[0] for r in self.conn.execute(
            "SELECT hub_name FROM hubs ORDER BY hub_name"
        ).fetchall()]

    def count_hubs(self):
        return self.conn.execute("SELECT COUNT(*) FROM hubs").fetchone()[0]

    def get_hub(self, hub_id):
        r = self.conn.execute(
            "SELECT * FROM hubs WHERE hub_id=?", (int(hub_id),)
        ).fetchone()
        return dict(r) if r else None

    def add_hub(self, hub_id, hub_name):
        try:
            self.conn.execute(
                "INSERT INTO hubs (hub_id, hub_name, created_at) VALUES (?, ?, ?)",
                (int(hub_id), hub_name, _now()),
            )
            self.conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False

    def upsert_hub(self, hub_id, hub_name):
        """Insert, or rename an existing hub_id (also re-files apartments that
        were under the old name). Raises IntegrityError if the name is already
        taken by a different hub_id."""
        hid = int(hub_id)
        row = self.conn.execute("SELECT hub_name FROM hubs WHERE hub_id=?", (hid,)).fetchone()
        if row:
            old_name = row[0]
            self.conn.execute("UPDATE hubs SET hub_name=? WHERE hub_id=?", (hub_name, hid))
            if old_name != hub_name:
                self.conn.execute(
                    "UPDATE apartments SET hub=? WHERE hub=?", (hub_name, old_name)
                )
        else:
            self.conn.execute(
                "INSERT INTO hubs (hub_id, hub_name, created_at) VALUES (?, ?, ?)",
                (hid, hub_name, _now()),
            )
        self.conn.commit()

    def delete_hub(self, hub_id):
        self.conn.execute("DELETE FROM hubs WHERE hub_id=?", (int(hub_id),))
        self.conn.commit()

    # ── apartments ───────────────────────────────────────────────────────
    def add_apartment(self, name, hub, location_link, created_by, apartment_code=""):
        cur = self.conn.execute(
            "INSERT INTO apartments (name, apartment_code, hub, location_link, created_by, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (name, apartment_code, hub, location_link, created_by, _now()),
        )
        self.conn.commit()
        return cur.lastrowid

    def bulk_add_apartments(self, rows, created_by):
        """rows: iterable of (name, hub, location_link, apartment_code)."""
        now = _now()
        self.conn.executemany(
            "INSERT INTO apartments (name, hub, location_link, apartment_code, created_by, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            [(n, h, l, c, created_by, now) for (n, h, l, c) in rows],
        )
        self.conn.commit()
        return len(rows)

    def get_apartment_by_code(self, code):
        if not code:
            return None
        r = self.conn.execute(
            "SELECT * FROM apartments WHERE apartment_code=? ORDER BY id LIMIT 1", (code,)
        ).fetchone()
        return dict(r) if r else None

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

    def update_apartment(self, apt_id, name=None, hub=None, location_link=None, apartment_code=None):
        sets, vals = [], []
        for col, val in (
            ("name", name), ("hub", hub),
            ("location_link", location_link), ("apartment_code", apartment_code),
        ):
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

    def request_recollect(self, apt_id, assigned_to, requested_by):
        """Send an apartment back to a BTL coordinator for a fresh contact number.
        Keeps the existing collection on file; flags the apartment so BTL sees why."""
        self.conn.execute(
            "UPDATE apartments SET assigned_to=?, status=?, recollect_at=? WHERE id=?",
            (assigned_to, STATUS_PENDING, _now(), int(apt_id)),
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

    def save_collection(self, apartment_id, outcome, contact_name, phone, designation,
                        total_units, no_number_reason, campaigns, collected_by):
        apartment_id = int(apartment_id)
        now = _now()
        total_units = int(total_units or 0)
        row = self.conn.execute(
            "SELECT * FROM collections WHERE apartment_id=?", (apartment_id,)
        ).fetchone()
        existing = dict(row) if row else None
        if existing:
            cid = existing["id"]
            pn, pp, ps = _prev_contact_shift(existing, phone)
            self.conn.execute(
                "UPDATE collections SET outcome=?, contact_name=?, phone=?, designation=?, "
                "total_units=?, no_number_reason=?, previous_contact_name=?, previous_phone=?, "
                "previous_saved_at=?, collected_by=?, updated_at=? WHERE id=?",
                (outcome, contact_name, phone, designation, total_units, no_number_reason,
                 pn, pp, ps, collected_by, now, cid),
            )
        else:
            cur = self.conn.execute(
                "INSERT INTO collections (apartment_id, outcome, contact_name, phone, designation, "
                "total_units, no_number_reason, collected_by, collected_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (apartment_id, outcome, contact_name, phone, designation, total_units,
                 no_number_reason, collected_by, now, now),
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
            "UPDATE apartments SET status=?, recollect_at='' WHERE id=?",
            (_status_for(outcome), apartment_id),
        )
        self.conn.commit()
        return cid

    def upsert_contact(self, apartment_id, contact_name, designation, phone, updated_by):
        """Marketing bulk-upload path: sets contact fields only, never touches campaigns.
        A changed number pushes the old one into previous_phone."""
        apartment_id = int(apartment_id)
        now = _now()
        row = self.conn.execute(
            "SELECT * FROM collections WHERE apartment_id=?", (apartment_id,)
        ).fetchone()
        existing = dict(row) if row else None
        if existing:
            pn, pp, ps = _prev_contact_shift(existing, phone)
            self.conn.execute(
                "UPDATE collections SET outcome='number', contact_name=?, designation=?, "
                "phone=?, previous_contact_name=?, previous_phone=?, previous_saved_at=?, "
                "updated_at=? WHERE id=?",
                (contact_name, designation, phone, pn, pp, ps, now, existing["id"]),
            )
        else:
            self.conn.execute(
                "INSERT INTO collections (apartment_id, outcome, contact_name, phone, "
                "designation, collected_by, collected_at, updated_at) "
                "VALUES (?, 'number', ?, ?, ?, ?, ?, ?)",
                (apartment_id, contact_name, phone, designation, updated_by, now, now),
            )
        self.conn.execute(
            "UPDATE apartments SET status=?, recollect_at='' WHERE id=?",
            (STATUS_COLLECTED, apartment_id),
        )
        self.conn.commit()

    # ── standees ─────────────────────────────────────────────────────────
    def add_standee(self, name, photo_path, total_units, storage_location, created_by):
        try:
            cur = self.conn.execute(
                "INSERT INTO standees (name, photo_path, total_units, storage_location, "
                "created_by, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (name, photo_path, int(total_units), storage_location, created_by, _now()),
            )
            self.conn.commit()
            return cur.lastrowid
        except sqlite3.IntegrityError:
            return None

    def list_standees(self):
        rows = self.conn.execute("SELECT * FROM standees ORDER BY name").fetchall()
        return [dict(r) for r in rows]

    def get_standee(self, standee_id):
        r = self.conn.execute("SELECT * FROM standees WHERE id=?", (int(standee_id),)).fetchone()
        return dict(r) if r else None

    def retire_standee(self, standee_id, replaced_by=None):
        self.conn.execute(
            "UPDATE standees SET active=0, replaced_by=? WHERE id=?",
            (int(replaced_by) if replaced_by else None, int(standee_id)),
        )
        self.conn.commit()

    def update_standee(self, standee_id, name=None, total_units=None,
                       storage_location=None, photo_path=None):
        sets, vals = [], []
        for col, val in (
            ("name", name), ("total_units", total_units),
            ("storage_location", storage_location), ("photo_path", photo_path),
        ):
            if val is not None:
                sets.append(f"{col}=?")
                vals.append(int(val) if col == "total_units" else val)
        if not sets:
            return True
        vals.append(int(standee_id))
        try:
            self.conn.execute(f"UPDATE standees SET {', '.join(sets)} WHERE id=?", vals)
            self.conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False

    def standee_in_use(self, standee_id):
        """Assignments referencing it + standees that name it as their replacement."""
        sid = int(standee_id)
        a = self.conn.execute(
            "SELECT COUNT(*) FROM standee_assignments WHERE standee_id=?", (sid,)
        ).fetchone()[0]
        r = self.conn.execute(
            "SELECT COUNT(*) FROM standees WHERE replaced_by=?", (sid,)
        ).fetchone()[0]
        return a + r

    def delete_standee(self, standee_id):
        sid = int(standee_id)
        self.conn.execute("DELETE FROM standee_reprints WHERE standee_id=?", (sid,))
        self.conn.execute("DELETE FROM standees WHERE id=?", (sid,))
        self.conn.commit()

    def reprint_standee(self, standee_id, added_units, note, added_by, resolve_damaged=False):
        standee_id = int(standee_id)
        added_units = int(added_units)
        self.conn.execute(
            "INSERT INTO standee_reprints (standee_id, added_units, note, added_by, added_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (standee_id, added_units, note, added_by, _now()),
        )
        self.conn.execute(
            "UPDATE standees SET total_units = total_units + ? WHERE id=?",
            (added_units, standee_id),
        )
        if resolve_damaged:
            current_damaged = self.standee_stats().get(standee_id, {}).get("damaged", 0)
            resolve_amt = min(added_units, current_damaged)
            if resolve_amt > 0:
                self.conn.execute(
                    "UPDATE standees SET damaged_resolved = damaged_resolved + ? WHERE id=?",
                    (resolve_amt, standee_id),
                )
        self.conn.commit()

    def reprint_history(self, standee_id):
        rows = self.conn.execute(
            "SELECT * FROM standee_reprints WHERE standee_id=? ORDER BY id DESC", (int(standee_id),)
        ).fetchall()
        return [dict(r) for r in rows]

    def standee_stats(self):
        """{standee_id: {placed, damaged, damaged_raw, lost, available}}

        `damaged` is the displayed count (raw damaged minus units already covered
        by a "reprint to replace damaged" action) — a dismissible indicator.
        `available` is always computed off the raw damaged count: printing
        replacements doesn't un-damage the physical units still sitting around,
        so it must not be double-counted into availability. A discontinued
        (inactive) standee always reports `available: 0` — those units can
        never be assigned again regardless of the arithmetic, so nothing about
        it should look "ready to use" anywhere in the app.
        """
        placed, damaged_raw, lost = {}, {}, {}
        for r in self.conn.execute(
            "SELECT standee_id, SUM(quantity) q FROM standee_assignments "
            "WHERE status='Placed' GROUP BY standee_id"
        ):
            placed[r["standee_id"]] = r["q"] or 0
        for r in self.conn.execute(
            "SELECT standee_id, quantity, quantity_returned, quantity_damaged, quantity_missing "
            "FROM standee_assignments WHERE status='Collected'"
        ):
            sid = r["standee_id"]
            damaged_raw[sid] = damaged_raw.get(sid, 0) + (r["quantity_damaged"] or 0)
            explicit = r["quantity_missing"] or 0
            implicit = (r["quantity"] or 0) - (r["quantity_returned"] or 0) - (r["quantity_damaged"] or 0)
            missing = explicit if explicit else max(0, implicit)
            if missing > 0:
                lost[sid] = lost.get(sid, 0) + missing
        out = {}
        for s in self.list_standees():
            sid = s["id"]
            p, d_raw, l = placed.get(sid, 0), damaged_raw.get(sid, 0), lost.get(sid, 0)
            resolved = min(s.get("damaged_resolved") or 0, d_raw)
            available = (s["total_units"] - p - d_raw - l) if s.get("active") else 0
            out[sid] = {
                "placed": p, "damaged": d_raw - resolved, "damaged_raw": d_raw, "lost": l,
                "available": available,
            }
        return out

    def active_standee_placements(self):
        rows = self.conn.execute(
            """SELECT sa.standee_id, s.name AS standee_name, s.photo_path AS standee_photo,
                      sa.apartment_id, a.name AS apartment_name, a.hub AS apartment_hub, sa.quantity
               FROM standee_assignments sa
               JOIN standees s ON s.id = sa.standee_id
               JOIN apartments a ON a.id = sa.apartment_id
               WHERE sa.status='Placed' ORDER BY a.name"""
        ).fetchall()
        return [dict(r) for r in rows]

    def create_standee_assignment(self, standee_id, apartment_id, assigned_to, quantity,
                                   duration_days, collection_location, created_by,
                                   invoice_photo="", invoice_note=""):
        now = _now()
        cur = self.conn.execute(
            "INSERT INTO standee_assignments (standee_id, apartment_id, assigned_to, quantity, "
            "duration_days, collection_location, status, invoice_photo, invoice_note, "
            "created_by, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, 'Assigned', ?, ?, ?, ?, ?)",
            (int(standee_id), int(apartment_id), assigned_to, int(quantity),
             int(duration_days), collection_location, invoice_photo, invoice_note,
             created_by, now, now),
        )
        self.conn.commit()
        return cur.lastrowid

    def set_assignment_invoice(self, assignment_id, invoice_photo, invoice_note, updated_by):
        """Update the payment-proof photo (only if a new one is given) + note."""
        sets, vals = ["invoice_note=?", "updated_at=?"], [invoice_note, _now()]
        if invoice_photo:
            sets.insert(0, "invoice_photo=?")
            vals.insert(0, invoice_photo)
        vals.append(int(assignment_id))
        self.conn.execute(
            f"UPDATE standee_assignments SET {', '.join(sets)} WHERE id=?", vals
        )
        self.conn.commit()

    def list_standee_assignments(self):
        rows = self.conn.execute(
            """SELECT sa.*, s.name AS standee_name, s.photo_path AS standee_photo,
                      a.name AS apartment_name, a.hub AS apartment_hub
               FROM standee_assignments sa
               JOIN standees s ON s.id = sa.standee_id
               JOIN apartments a ON a.id = sa.apartment_id
               ORDER BY sa.id DESC"""
        ).fetchall()
        return [dict(r) for r in rows]

    def list_standee_assignments_for_btl(self, username):
        rows = self.conn.execute(
            """SELECT sa.*, s.name AS standee_name, s.photo_path AS standee_photo,
                      a.name AS apartment_name, a.hub AS apartment_hub,
                      a.location_link AS apartment_location_link
               FROM standee_assignments sa
               JOIN standees s ON s.id = sa.standee_id
               JOIN apartments a ON a.id = sa.apartment_id
               WHERE sa.assigned_to=? ORDER BY sa.id DESC""",
            (username,),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_standee_assignment(self, assignment_id):
        r = self.conn.execute(
            """SELECT sa.*, s.name AS standee_name, s.photo_path AS standee_photo,
                      a.name AS apartment_name, a.hub AS apartment_hub,
                      a.location_link AS apartment_location_link
               FROM standee_assignments sa
               JOIN standees s ON s.id = sa.standee_id
               JOIN apartments a ON a.id = sa.apartment_id
               WHERE sa.id=?""",
            (int(assignment_id),),
        ).fetchone()
        return dict(r) if r else None

    def update_assignment_quantity(self, assignment_id, quantity):
        self.conn.execute(
            "UPDATE standee_assignments SET quantity=?, updated_at=? WHERE id=?",
            (int(quantity), _now(), int(assignment_id)),
        )
        self.conn.commit()

    def confirm_placement(self, assignment_id, placed_by, photo_paths):
        assignment_id = int(assignment_id)
        row = self.conn.execute(
            "SELECT duration_days FROM standee_assignments WHERE id=?", (assignment_id,)
        ).fetchone()
        now = _now()
        collect_by = (
            datetime.now(IST) + timedelta(days=int(row["duration_days"] or 0))
        ).strftime("%Y-%m-%d") if row else ""
        self.conn.execute(
            "UPDATE standee_assignments SET status='Placed', placed_at=?, placed_by=?, "
            "collect_by=?, updated_at=? WHERE id=?",
            (now, placed_by, collect_by, now, assignment_id),
        )
        for p in photo_paths:
            self.conn.execute(
                "INSERT INTO standee_photos (assignment_id, kind, path, uploaded_at) "
                "VALUES (?, 'placement', ?, ?)",
                (assignment_id, p, now),
            )
        self.conn.commit()

    def collect_standee_assignment(self, assignment_id, quantity_returned, quantity_damaged,
                                    damage_note, drop_location, collected_by, photo_paths,
                                    quantity_missing=0, redeployed_to=None):
        assignment_id = int(assignment_id)
        now = _now()
        self.conn.execute(
            "UPDATE standee_assignments SET status='Collected', collected_at=?, collected_by=?, "
            "quantity_returned=?, quantity_damaged=?, quantity_missing=?, damage_note=?, "
            "drop_location=?, redeployed_to=?, updated_at=? WHERE id=?",
            (now, collected_by, int(quantity_returned), int(quantity_damaged),
             int(quantity_missing), damage_note, drop_location,
             int(redeployed_to) if redeployed_to else None, now, assignment_id),
        )
        for p in photo_paths:
            self.conn.execute(
                "INSERT INTO standee_photos (assignment_id, kind, path, uploaded_at) "
                "VALUES (?, 'damage', ?, ?)",
                (assignment_id, p, now),
            )
        self.conn.commit()

    def photos_for(self, assignment_id):
        rows = self.conn.execute(
            "SELECT * FROM standee_photos WHERE assignment_id=? ORDER BY id", (int(assignment_id),)
        ).fetchall()
        return [dict(r) for r in rows]

    # ── media (local dev writes to disk in app._save_photos; nothing to do here) ──
    def ensure_media_bucket(self):
        return None


MEDIA_BUCKET = "media"


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
                "workspace": workspace, "is_admin": False, "active": True, "created_at": _now(),
            }).execute()
            return r.data[0]["id"] if r.data else None
        except Exception:
            return None

    def set_user_active(self, user_id, active):
        self.sb.table("users").update({"active": bool(active)}).eq("id", int(user_id)).execute()

    def set_user_password(self, user_id, password_hash):
        self.sb.table("users").update({"password_hash": password_hash}).eq("id", int(user_id)).execute()

    # ── admin + per-feature permissions ──
    def count_admins(self):
        r = (
            self.sb.table("users").select("id", count="exact")
            .eq("is_admin", True).eq("active", True).limit(1).execute()
        )
        return r.count or 0

    def set_user_admin(self, user_id, is_admin):
        self.sb.table("users").update({"is_admin": bool(is_admin)}).eq("id", int(user_id)).execute()

    def promote_to_admin(self, username):
        self.sb.table("users").update({"is_admin": True}).eq("username", username).execute()

    def list_permissions(self, username):
        rows = (
            self.sb.table("user_permissions").select("feature,level")
            .eq("username", username).execute().data
        )
        return {r["feature"]: r["level"] for r in rows}

    def get_permission(self, username, feature):
        r = (
            self.sb.table("user_permissions").select("level")
            .eq("username", username).eq("feature", feature).limit(1).execute()
        )
        return r.data[0]["level"] if r.data else None

    def set_permission(self, username, feature, level):
        self.sb.table("user_permissions").upsert(
            {"username": username, "feature": feature, "level": level},
            on_conflict="username,feature",
        ).execute()

    def set_permissions(self, username, mapping):
        for feature, level in mapping.items():
            self.set_permission(username, feature, level)

    def clear_permissions(self, username):
        self.sb.table("user_permissions").delete().eq("username", username).execute()

    # ── hubs ──
    def list_hubs(self):
        return (
            self.sb.table("hubs").select("hub_id,hub_name").order("hub_name").execute().data
        )

    def hub_names(self):
        return [r["hub_name"] for r in self.list_hubs()]

    def count_hubs(self):
        r = self.sb.table("hubs").select("hub_id", count="exact").limit(1).execute()
        return r.count or 0

    def get_hub(self, hub_id):
        r = self.sb.table("hubs").select("*").eq("hub_id", int(hub_id)).limit(1).execute()
        return r.data[0] if r.data else None

    def add_hub(self, hub_id, hub_name):
        try:
            self.sb.table("hubs").insert({
                "hub_id": int(hub_id), "hub_name": hub_name, "created_at": _now(),
            }).execute()
            return True
        except Exception:
            return False

    def upsert_hub(self, hub_id, hub_name):
        existing = self.get_hub(int(hub_id))
        self.sb.table("hubs").upsert(
            {"hub_id": int(hub_id), "hub_name": hub_name}, on_conflict="hub_id"
        ).execute()
        if existing and existing.get("hub_name") not in (None, hub_name):
            self.sb.table("apartments").update({"hub": hub_name}).eq(
                "hub", existing["hub_name"]
            ).execute()

    def delete_hub(self, hub_id):
        self.sb.table("hubs").delete().eq("hub_id", int(hub_id)).execute()

    # ── apartments ──
    def add_apartment(self, name, hub, location_link, created_by, apartment_code=""):
        r = self.sb.table("apartments").insert({
            "name": name, "apartment_code": apartment_code, "hub": hub,
            "location_link": location_link,
            "assigned_to": "", "status": STATUS_PENDING, "deleted": False,
            "created_by": created_by, "created_at": _now(),
        }).execute()
        return r.data[0]["id"] if r.data else None

    def bulk_add_apartments(self, rows, created_by):
        """rows: iterable of (name, hub, location_link, apartment_code)."""
        now = _now()
        payload = [{
            "name": n, "hub": h, "location_link": l, "apartment_code": c,
            "assigned_to": "", "status": STATUS_PENDING, "deleted": False,
            "created_by": created_by, "created_at": now,
        } for (n, h, l, c) in rows]
        if payload:
            self.sb.table("apartments").insert(payload).execute()
        return len(payload)

    def get_apartment_by_code(self, code):
        if not code:
            return None
        r = (
            self.sb.table("apartments").select("*")
            .eq("apartment_code", code).order("id").limit(1).execute()
        )
        return r.data[0] if r.data else None

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

    def update_apartment(self, apt_id, name=None, hub=None, location_link=None, apartment_code=None):
        upd = {}
        if name is not None:
            upd["name"] = name
        if hub is not None:
            upd["hub"] = hub
        if location_link is not None:
            upd["location_link"] = location_link
        if apartment_code is not None:
            upd["apartment_code"] = apartment_code
        if upd:
            self.sb.table("apartments").update(upd).eq("id", int(apt_id)).execute()

    def assign_apartments(self, apt_ids, assigned_to):
        for i in (int(x) for x in apt_ids):
            self.sb.table("apartments").update(
                {"assigned_to": assigned_to, "status": STATUS_PENDING}
            ).eq("id", i).execute()

    def request_recollect(self, apt_id, assigned_to, requested_by):
        self.sb.table("apartments").update({
            "assigned_to": assigned_to, "status": STATUS_PENDING, "recollect_at": _now(),
        }).eq("id", int(apt_id)).execute()

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

    def save_collection(self, apartment_id, outcome, contact_name, phone, designation,
                        total_units, no_number_reason, campaigns, collected_by):
        apartment_id = int(apartment_id)
        now = _now()
        existing = self.sb.table("collections").select("*").eq("apartment_id", apartment_id).limit(1).execute()
        row = {
            "outcome": outcome, "contact_name": contact_name, "phone": phone,
            "designation": designation, "total_units": int(total_units or 0),
            "no_number_reason": no_number_reason,
            "collected_by": collected_by, "updated_at": now,
        }
        if existing.data:
            cid = existing.data[0]["id"]
            pn, pp, ps = _prev_contact_shift(existing.data[0], phone)
            row.update({"previous_contact_name": pn, "previous_phone": pp, "previous_saved_at": ps})
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

        self.sb.table("apartments").update(
            {"status": _status_for(outcome), "recollect_at": ""}
        ).eq("id", apartment_id).execute()
        return cid

    def upsert_contact(self, apartment_id, contact_name, designation, phone, updated_by):
        apartment_id = int(apartment_id)
        now = _now()
        existing = self.sb.table("collections").select("*").eq("apartment_id", apartment_id).limit(1).execute()
        if existing.data:
            pn, pp, ps = _prev_contact_shift(existing.data[0], phone)
            self.sb.table("collections").update({
                "outcome": "number", "contact_name": contact_name,
                "designation": designation, "phone": phone,
                "previous_contact_name": pn, "previous_phone": pp, "previous_saved_at": ps,
                "updated_at": now,
            }).eq("id", existing.data[0]["id"]).execute()
        else:
            self.sb.table("collections").insert({
                "apartment_id": apartment_id, "outcome": "number", "contact_name": contact_name,
                "phone": phone, "designation": designation, "collected_by": updated_by,
                "collected_at": now, "updated_at": now,
            }).execute()
        self.sb.table("apartments").update(
            {"status": STATUS_COLLECTED, "recollect_at": ""}
        ).eq("id", apartment_id).execute()

    # ── standees ──
    def add_standee(self, name, photo_path, total_units, storage_location, created_by):
        try:
            r = self.sb.table("standees").insert({
                "name": name, "photo_path": photo_path, "total_units": int(total_units),
                "storage_location": storage_location, "created_by": created_by, "created_at": _now(),
            }).execute()
            return r.data[0]["id"] if r.data else None
        except Exception:
            return None

    def list_standees(self):
        return self.sb.table("standees").select("*").order("name").execute().data

    def get_standee(self, standee_id):
        r = self.sb.table("standees").select("*").eq("id", int(standee_id)).limit(1).execute()
        return r.data[0] if r.data else None

    def retire_standee(self, standee_id, replaced_by=None):
        self.sb.table("standees").update({
            "active": False, "replaced_by": int(replaced_by) if replaced_by else None,
        }).eq("id", int(standee_id)).execute()

    def update_standee(self, standee_id, name=None, total_units=None,
                       storage_location=None, photo_path=None):
        upd = {}
        if name is not None:
            upd["name"] = name
        if total_units is not None:
            upd["total_units"] = int(total_units)
        if storage_location is not None:
            upd["storage_location"] = storage_location
        if photo_path is not None:
            upd["photo_path"] = photo_path
        if not upd:
            return True
        try:
            self.sb.table("standees").update(upd).eq("id", int(standee_id)).execute()
            return True
        except Exception:
            return False

    def standee_in_use(self, standee_id):
        sid = int(standee_id)
        a = (self.sb.table("standee_assignments").select("id", count="exact")
             .eq("standee_id", sid).limit(1).execute().count) or 0
        r = (self.sb.table("standees").select("id", count="exact")
             .eq("replaced_by", sid).limit(1).execute().count) or 0
        return a + r

    def delete_standee(self, standee_id):
        sid = int(standee_id)
        self.sb.table("standee_reprints").delete().eq("standee_id", sid).execute()
        self.sb.table("standees").delete().eq("id", sid).execute()

    def reprint_standee(self, standee_id, added_units, note, added_by, resolve_damaged=False):
        standee_id = int(standee_id)
        added_units = int(added_units)
        self.sb.table("standee_reprints").insert({
            "standee_id": standee_id, "added_units": added_units, "note": note,
            "added_by": added_by, "added_at": _now(),
        }).execute()
        s = self.get_standee(standee_id)
        new_total = (s["total_units"] if s else 0) + added_units
        self.sb.table("standees").update({"total_units": new_total}).eq("id", standee_id).execute()
        if resolve_damaged:
            current_damaged = self.standee_stats().get(standee_id, {}).get("damaged", 0)
            resolve_amt = min(added_units, current_damaged)
            if resolve_amt > 0:
                new_resolved = ((s.get("damaged_resolved") or 0) if s else 0) + resolve_amt
                self.sb.table("standees").update({"damaged_resolved": new_resolved}).eq("id", standee_id).execute()

    def reprint_history(self, standee_id):
        return (
            self.sb.table("standee_reprints").select("*").eq("standee_id", int(standee_id))
            .order("id", desc=True).execute().data
        )

    def standee_stats(self):
        placed, damaged_raw, lost = {}, {}, {}
        for r in self.sb.table("standee_assignments").select("standee_id,quantity").eq("status", "Placed").execute().data:
            placed[r["standee_id"]] = placed.get(r["standee_id"], 0) + (r["quantity"] or 0)
        for r in self.sb.table("standee_assignments").select(
            "standee_id,quantity,quantity_returned,quantity_damaged,quantity_missing"
        ).eq("status", "Collected").execute().data:
            sid = r["standee_id"]
            damaged_raw[sid] = damaged_raw.get(sid, 0) + (r["quantity_damaged"] or 0)
            explicit = r.get("quantity_missing") or 0
            implicit = (r["quantity"] or 0) - (r["quantity_returned"] or 0) - (r["quantity_damaged"] or 0)
            missing = explicit if explicit else max(0, implicit)
            if missing > 0:
                lost[sid] = lost.get(sid, 0) + missing
        out = {}
        for s in self.list_standees():
            sid = s["id"]
            p, d_raw, l = placed.get(sid, 0), damaged_raw.get(sid, 0), lost.get(sid, 0)
            resolved = min(s.get("damaged_resolved") or 0, d_raw)
            available = (s["total_units"] - p - d_raw - l) if s.get("active") else 0
            out[sid] = {
                "placed": p, "damaged": d_raw - resolved, "damaged_raw": d_raw, "lost": l,
                "available": available,
            }
        return out

    def active_standee_placements(self):
        try:
            rows = self.sb.table("standee_assignments").select(
                "standee_id, quantity, standees!inner(name,photo_path), apartment_id, apartments!inner(name,hub)"
            ).eq("status", "Placed").execute().data
        except Exception:
            return []
        out = [{
            "standee_id": r["standee_id"], "standee_name": r["standees"]["name"],
            "standee_photo": r["standees"].get("photo_path", ""),
            "apartment_id": r["apartment_id"], "apartment_name": r["apartments"]["name"],
            "apartment_hub": r["apartments"]["hub"], "quantity": r["quantity"],
        } for r in rows]
        out.sort(key=lambda x: x["apartment_name"])
        return out

    def create_standee_assignment(self, standee_id, apartment_id, assigned_to, quantity,
                                   duration_days, collection_location, created_by,
                                   invoice_photo="", invoice_note=""):
        now = _now()
        r = self.sb.table("standee_assignments").insert({
            "standee_id": int(standee_id), "apartment_id": int(apartment_id),
            "assigned_to": assigned_to, "quantity": int(quantity),
            "duration_days": int(duration_days), "collection_location": collection_location,
            "status": "Assigned", "invoice_photo": invoice_photo, "invoice_note": invoice_note,
            "created_by": created_by, "created_at": now, "updated_at": now,
        }).execute()
        return r.data[0]["id"] if r.data else None

    def set_assignment_invoice(self, assignment_id, invoice_photo, invoice_note, updated_by):
        upd = {"invoice_note": invoice_note, "updated_at": _now()}
        if invoice_photo:
            upd["invoice_photo"] = invoice_photo
        self.sb.table("standee_assignments").update(upd).eq("id", int(assignment_id)).execute()

    def _join_assignment_rows(self, rows):
        out = []
        for r in rows:
            d = dict(r)
            std = r.get("standees") or {}
            d["standee_name"] = std.get("name", "")
            d["standee_photo"] = std.get("photo_path", "")
            apt = r.get("apartments") or {}
            d["apartment_name"] = apt.get("name", "")
            d["apartment_hub"] = apt.get("hub", "")
            d["apartment_location_link"] = apt.get("location_link", "")
            out.append(d)
        return out

    def list_standee_assignments(self):
        rows = self.sb.table("standee_assignments").select(
            "*, standees!inner(name,photo_path), apartments!inner(name,hub)"
        ).order("id", desc=True).execute().data
        return self._join_assignment_rows(rows)

    def list_standee_assignments_for_btl(self, username):
        rows = self.sb.table("standee_assignments").select(
            "*, standees!inner(name,photo_path), apartments!inner(name,hub,location_link)"
        ).eq("assigned_to", username).order("id", desc=True).execute().data
        return self._join_assignment_rows(rows)

    def get_standee_assignment(self, assignment_id):
        rows = self.sb.table("standee_assignments").select(
            "*, standees!inner(name,photo_path), apartments!inner(name,hub,location_link)"
        ).eq("id", int(assignment_id)).limit(1).execute().data
        joined = self._join_assignment_rows(rows)
        return joined[0] if joined else None

    def update_assignment_quantity(self, assignment_id, quantity):
        self.sb.table("standee_assignments").update(
            {"quantity": int(quantity), "updated_at": _now()}
        ).eq("id", int(assignment_id)).execute()

    def confirm_placement(self, assignment_id, placed_by, photo_paths):
        assignment_id = int(assignment_id)
        r = self.sb.table("standee_assignments").select("duration_days").eq("id", assignment_id).limit(1).execute()
        duration = r.data[0]["duration_days"] if r.data else 0
        now = _now()
        collect_by = (datetime.now(IST) + timedelta(days=int(duration or 0))).strftime("%Y-%m-%d")
        self.sb.table("standee_assignments").update({
            "status": "Placed", "placed_at": now, "placed_by": placed_by,
            "collect_by": collect_by, "updated_at": now,
        }).eq("id", assignment_id).execute()
        if photo_paths:
            self.sb.table("standee_photos").insert([
                {"assignment_id": assignment_id, "kind": "placement", "path": p, "uploaded_at": now}
                for p in photo_paths
            ]).execute()

    def collect_standee_assignment(self, assignment_id, quantity_returned, quantity_damaged,
                                    damage_note, drop_location, collected_by, photo_paths,
                                    quantity_missing=0, redeployed_to=None):
        assignment_id = int(assignment_id)
        now = _now()
        self.sb.table("standee_assignments").update({
            "status": "Collected", "collected_at": now, "collected_by": collected_by,
            "quantity_returned": int(quantity_returned), "quantity_damaged": int(quantity_damaged),
            "quantity_missing": int(quantity_missing),
            "damage_note": damage_note, "drop_location": drop_location,
            "redeployed_to": int(redeployed_to) if redeployed_to else None,
            "updated_at": now,
        }).eq("id", assignment_id).execute()
        if photo_paths:
            self.sb.table("standee_photos").insert([
                {"assignment_id": assignment_id, "kind": "damage", "path": p, "uploaded_at": now}
                for p in photo_paths
            ]).execute()

    def photos_for(self, assignment_id):
        return (
            self.sb.table("standee_photos").select("*").eq("assignment_id", int(assignment_id))
            .order("id").execute().data
        )

    # ── media: a public Storage bucket, so uploads survive Render redeploys ──
    def ensure_media_bucket(self):
        try:
            self.sb.storage.create_bucket(
                MEDIA_BUCKET,
                options={
                    "public": True,
                    "file_size_limit": 20 * 1024 * 1024,
                    "allowed_mime_types": [
                        "image/jpeg", "image/png", "image/webp",
                        "image/gif", "image/heic",
                    ],
                },
            )
        except Exception:
            pass  # already exists (or perms) — fine

    def upload_media(self, key, data, content_type):
        """Upload bytes to the public 'media' bucket; return the public URL."""
        self.sb.storage.from_(MEDIA_BUCKET).upload(
            key, data,
            {"content-type": content_type or "application/octet-stream", "upsert": "true"},
        )
        url = self.sb.storage.from_(MEDIA_BUCKET).get_public_url(key)
        return (url or "").rstrip("?")


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


def ensure_seed_hubs():
    """Populate the hubs table from config.HUBS_SEED on first run (empty table)."""
    d = get_db()
    try:
        if d.count_hubs() > 0:
            return
    except Exception:
        return
    from config import HUBS_SEED
    for hid, hname in HUBS_SEED:
        d.add_hub(hid, hname)


def ensure_admin():
    """Make sure at least one admin exists. Promotes ADMIN_USERNAME (default
    'gowtham') if it's a marketing user and nobody is admin yet."""
    d = get_db()
    try:
        if d.count_admins() > 0:
            return
    except Exception:
        return
    username = (os.environ.get("ADMIN_USERNAME", "gowtham").strip() or "gowtham")
    u = d.get_user(username)
    if u and u.get("workspace") == "marketing":
        d.promote_to_admin(username)
