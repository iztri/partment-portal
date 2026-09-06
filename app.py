"""Marketing + BTL apartment campaign portal.

Run locally:  PORT=5055 python3 app.py
"""

import os
import uuid
from datetime import date
from io import BytesIO

from flask import (
    Flask, render_template, request, redirect, url_for, session, flash, send_file
)
from auth import (
    login_required, role_required, feature_required, admin_required,
    authenticate, logout, ensure_seed_admin, hash_password,
    effective_level, is_admin_user,
)
from db import get_db, ensure_seed_hubs, ensure_admin
from config import (
    MARKETING_CAMPAIGNS, DESIGNATIONS, WORKSPACE_LABELS,
    STATUS_PENDING, STATUS_COLLECTED, STATUS_NO_NUMBER,
    MARKETING_FEATURES, MARKETING_FEATURE_KEYS, PERMISSION_LEVELS, PERMISSION_RANK,
)

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET", "dev-only-change-me")
app.config["MAX_CONTENT_LENGTH"] = 20 * 1024 * 1024  # 20MB, generous for phone-camera photos

db = get_db()
ensure_seed_admin()
ensure_seed_hubs()
ensure_admin()

ALLOWED_IMAGE_EXT = {"jpg", "jpeg", "png", "webp", "gif", "heic"}


@app.context_processor
def _inject_access():
    """`can('hubs')` / `can('hubs','edit')` and `is_admin` for every template."""
    user = session.get("user")
    role = session.get("role")

    def can(feature, level="read"):
        if role != "marketing":
            return False
        return PERMISSION_RANK.get(effective_level(user, feature), 0) >= PERMISSION_RANK.get(level, 0)

    return {"can": can, "is_admin": bool(user) and is_admin_user(user)}


def _first_allowed_feature():
    for key in MARKETING_FEATURE_KEYS:
        if effective_level(session.get("user"), key) != "none":
            return key
    return None


# ── helpers ──────────────────────────────────────────────────────────────
def _campaigns_from_form():
    """Parse repeated campaign rows into [{campaign, price, days}], deduped."""
    names = request.form.getlist("campaign[]")
    prices = request.form.getlist("price[]")
    days = request.form.getlist("days[]")
    seen, out = set(), []
    for i, name in enumerate(names):
        name = (name or "").strip()
        if not name or name not in MARKETING_CAMPAIGNS or name in seen:
            continue
        seen.add(name)
        try:
            price = float(prices[i]) if i < len(prices) and prices[i] != "" else 0.0
        except ValueError:
            price = 0.0
        try:
            d = int(days[i]) if i < len(days) and days[i] != "" else 0
        except ValueError:
            d = 0
        out.append({"campaign": name, "price": price, "days": d})
    return out


def _apartment_stats(apartments):
    unassigned = [a for a in apartments if not a["assigned_to"]]
    assigned = [a for a in apartments if a["assigned_to"]]
    return {
        "total": len(apartments),
        "unassigned": len(unassigned),
        "pending": len([a for a in assigned if a["status"] == STATUS_PENDING]),
        "collected": len([a for a in assigned if a["status"] == STATUS_COLLECTED]),
        "no_number": len([a for a in assigned if a["status"] == STATUS_NO_NUMBER]),
    }


def _save_photos(files, subdir):
    """Save uploaded image files under static/uploads/standees/<subdir>/.
    Returns the list of saved paths, relative to the static folder."""
    saved = []
    folder = os.path.join(app.static_folder, "uploads", "standees", str(subdir))
    for f in files or []:
        if not f or not f.filename:
            continue
        ext = f.filename.rsplit(".", 1)[-1].lower() if "." in f.filename else ""
        if ext not in ALLOWED_IMAGE_EXT:
            continue
        os.makedirs(folder, exist_ok=True)
        fname = f"{uuid.uuid4().hex}.{ext}"
        f.save(os.path.join(folder, fname))
        saved.append(f"uploads/standees/{subdir}/{fname}")
    return saved


def _resolve_location_pair(select_name, detail_name):
    """hub-or-active-placement-or-custom pattern used by the standee location pickers."""
    hub = request.form.get(select_name, "").strip()
    detail = request.form.get(detail_name, "").strip()
    if hub == "__custom__":
        return detail
    if hub.startswith("apt:"):
        return hub[4:]
    if hub:
        return (hub + " - " + detail).strip(" -") if detail else hub
    return detail


# ── auth ─────────────────────────────────────────────────────────────────
@app.route("/login", methods=["GET", "POST"])
def login():
    if "user" in session:
        return redirect(url_for("home"))
    if request.method == "POST":
        if authenticate(request.form.get("username", ""), request.form.get("password", "")):
            flash(f"Welcome, {session['name']}", "success")
            return redirect(url_for("home"))
        flash("Invalid username or password", "danger")
    return render_template("login.html")


@app.route("/logout")
def do_logout():
    logout()
    return redirect(url_for("login"))


@app.route("/")
def home():
    if "user" not in session:
        return redirect(url_for("login"))
    if session["role"] != "marketing":
        return redirect(url_for("btl_dashboard"))
    first = _first_allowed_feature()
    dest = {
        "apartments": "marketing_dashboard", "hubs": "marketing_hubs_page",
        "assign": "marketing_assign_page", "standees": "marketing_standees_page",
        "export": "marketing_export_page",
    }.get(first)
    if dest:
        return redirect(url_for(dest))
    if is_admin_user(session["user"]):
        return redirect(url_for("marketing_team"))
    return render_template("error.html", code=403,
                           message="No sections are enabled for your account — ask an admin."), 403


# ═══════════════════════════════════════════════════════════════════════════
#  Marketing
# ═══════════════════════════════════════════════════════════════════════════
@app.route("/marketing")
@feature_required("apartments", "read")
def marketing_dashboard():
    apartments = db.list_apartments()
    collections = db.collections_by_apartment()
    return render_template(
        "marketing/dashboard.html",
        active="dashboard",
        apartments=apartments,
        collections=collections,
        stats=_apartment_stats(apartments),
        hub_names=db.hub_names(),
    )


@app.route("/marketing/add")
@feature_required("apartments", "edit")
def marketing_add_page():
    return render_template("marketing/add.html", active="add", hub_names=db.hub_names())


@app.route("/marketing/add", methods=["POST"])
@feature_required("apartments", "edit")
def marketing_add():
    name = request.form.get("name", "").strip()
    hub = request.form.get("hub", "").strip()
    link = request.form.get("location_link", "").strip()
    code = request.form.get("apartment_code", "").strip()
    if not name or hub not in set(db.hub_names()):
        flash("Apartment name and a valid hub are required", "danger")
        return redirect(url_for("marketing_add_page"))
    if code and db.get_apartment_by_code(code):
        flash(f"Apartment ID '{code}' is already used", "danger")
        return redirect(url_for("marketing_add_page"))
    db.add_apartment(name, hub, link, session["user"], apartment_code=code)
    flash(f"Added '{name}'", "success")
    return redirect(url_for("marketing_add_page"))


def _split_row(line):
    if "\t" in line:
        parts = line.split("\t")
    else:
        parts = line.split(",")
    return [p.strip() for p in parts]


@app.route("/marketing/bulk-upload", methods=["POST"])
@feature_required("apartments", "edit")
def marketing_bulk_upload():
    """Bulk apartments: Hub ID, Hub Name, Apartment ID, Apartment Name, Manager Name, Phone.
    Hub is matched by ID (auto-created from ID+Name if new); apartment is matched by
    Apartment ID (created or updated); manager name + phone go into the apartment's
    collection contact (designation left untouched)."""
    raw = request.form.get("bulk_data", "").strip()
    if not raw:
        flash("Nothing to upload", "danger")
        return redirect(url_for("marketing_add_page"))
    added = updated = contacts = 0
    errors = []
    for i, line in enumerate((l for l in raw.splitlines() if l.strip()), 1):
        p = _split_row(line)
        p += [""] * (6 - len(p))
        raw_hub_id, hub_name, apt_code, apt_name, mgr_name, phone = p[:6]
        # header row? (row 1, non-numeric Hub ID, mentions the column names)
        low = line.lower()
        if i == 1 and not raw_hub_id.lstrip("-").isdigit() and ("hub" in low or "apartment" in low):
            continue
        if not apt_name:
            errors.append(f"Row {i}: no apartment name — '{line}'")
            continue
        # resolve hub
        hub = None
        if raw_hub_id:
            try:
                hid = int(raw_hub_id)
            except ValueError:
                errors.append(f"Row {i}: bad Hub ID '{raw_hub_id}'")
                continue
            h = db.get_hub(hid)
            if h:
                hub = h["hub_name"]
            elif hub_name:
                db.add_hub(hid, hub_name)
                hub = hub_name
            else:
                errors.append(f"Row {i}: hub {hid} not found and no name to create it")
                continue
        elif hub_name and hub_name in set(db.hub_names()):
            hub = hub_name
        else:
            errors.append(f"Row {i}: no resolvable hub — '{line}'")
            continue
        # create or update apartment
        existing = db.get_apartment_by_code(apt_code) if apt_code else None
        if existing:
            db.update_apartment(existing["id"], name=apt_name, hub=hub)
            apt_id = existing["id"]
            updated += 1
        else:
            apt_id = db.add_apartment(apt_name, hub, "", session["user"], apartment_code=apt_code)
            added += 1
        # manager contact → collection (keep any existing designation)
        if mgr_name or phone:
            existing_col = db.get_collection(apt_id) or {}
            db.upsert_contact(apt_id, mgr_name, existing_col.get("designation", ""), phone, session["user"])
            contacts += 1
    msg = f"Added {added}, updated {updated} apartment(s); {contacts} manager contact(s)"
    if errors:
        msg += f" · skipped {len(errors)}: " + "; ".join(errors[:3])
    flash(msg, "success" if (added or updated) and not errors else "warning")
    return redirect(url_for("marketing_add_page"))


@app.route("/marketing/contacts/bulk-upload", methods=["POST"])
@feature_required("apartments", "edit")
def marketing_contacts_bulk_upload():
    raw = request.form.get("contacts_data", "").strip()
    if not raw:
        flash("Nothing to upload", "danger")
        return redirect(url_for("marketing_add_page"))
    apts_by_name = {a["name"].strip().lower(): a for a in db.list_apartments()}
    updated, errors = 0, []
    for i, line in enumerate((l for l in raw.splitlines() if l.strip()), 1):
        parts = [p.strip() for p in line.split(",")]
        if len(parts) < 4:
            errors.append(f"Row {i}: need 4 fields — '{line}'")
            continue
        apt_name, contact_name, designation, phone = parts[0], parts[1], parts[2], parts[3]
        apt = apts_by_name.get(apt_name.lower())
        if not apt:
            errors.append(f"Row {i}: no apartment named '{apt_name}'")
            continue
        if designation not in DESIGNATIONS:
            errors.append(f"Row {i}: invalid designation '{designation}'")
            continue
        db.upsert_contact(apt["id"], contact_name, designation, phone, session["user"])
        updated += 1
    msg = f"Updated {updated} contact(s)"
    if errors:
        msg += f" · skipped {len(errors)}: " + "; ".join(errors[:3])
    flash(msg, "success" if updated and not errors else "warning")
    return redirect(url_for("marketing_add_page"))


# ── Hubs (master apartment-grouping list) ────────────────────────────────
@app.route("/marketing/hubs")
@feature_required("hubs", "read")
def marketing_hubs_page():
    hubs = db.list_hubs()
    counts = {}
    for a in db.list_apartments():
        counts[a["hub"]] = counts.get(a["hub"], 0) + 1
    return render_template(
        "marketing/hubs.html", active="hubs",
        hubs=hubs, counts=counts,
    )


@app.route("/marketing/hubs/add", methods=["POST"])
@feature_required("hubs", "edit")
def marketing_hub_add():
    raw_id = request.form.get("hub_id", "").strip()
    hub_name = request.form.get("hub_name", "").strip()
    try:
        hub_id = int(raw_id)
    except ValueError:
        flash("Hub ID must be a whole number", "danger")
        return redirect(url_for("marketing_hubs_page"))
    if not hub_name:
        flash("Hub name is required", "danger")
    elif not db.add_hub(hub_id, hub_name):
        flash(f"Hub ID {hub_id} or name '{hub_name}' already exists", "danger")
    else:
        flash(f"Added hub {hub_id} · {hub_name}", "success")
    return redirect(url_for("marketing_hubs_page"))


@app.route("/marketing/hubs/bulk-upload", methods=["POST"])
@feature_required("hubs", "edit")
def marketing_hubs_bulk_upload():
    raw = request.form.get("bulk_data", "").strip()
    if not raw:
        flash("Nothing to upload", "danger")
        return redirect(url_for("marketing_hubs_page"))
    added = updated = 0
    errors = []
    for i, line in enumerate((l for l in raw.splitlines() if l.strip()), 1):
        if "\t" in line:
            parts = line.split("\t")
        elif "," in line:
            parts = line.split(",")
        else:
            parts = line.split(None, 1)
        parts = [p.strip() for p in parts if p.strip()]
        if len(parts) < 2:
            errors.append(f"Row {i}: '{line}'")
            continue
        try:
            hub_id = int(parts[0])
        except ValueError:
            # tolerate a header row like "Hub ID, Hub Name"
            if i == 1 and not parts[0][:1].isdigit():
                continue
            errors.append(f"Row {i}: bad ID '{parts[0]}'")
            continue
        hub_name = parts[1]
        existed = db.get_hub(hub_id) is not None
        try:
            db.upsert_hub(hub_id, hub_name)
        except Exception:
            errors.append(f"Row {i}: name '{hub_name}' is used by another hub")
            continue
        updated += 1 if existed else 0
        added += 0 if existed else 1
    msg = f"Added {added}, updated {updated} hub(s)"
    if errors:
        msg += f" · skipped {len(errors)}: " + "; ".join(errors[:3])
    flash(msg, "success" if (added or updated) and not errors else "warning")
    return redirect(url_for("marketing_hubs_page"))


@app.route("/marketing/hubs/<int:hub_id>/delete", methods=["POST"])
@feature_required("hubs", "read")
@admin_required
def marketing_hub_delete(hub_id):
    hub = db.get_hub(hub_id)
    if not hub:
        flash("Hub not found", "danger")
        return redirect(url_for("marketing_hubs_page"))
    in_use = sum(1 for a in db.list_apartments(include_deleted=True) if a["hub"] == hub["hub_name"])
    if in_use:
        flash(f"Can't delete '{hub['hub_name']}' — {in_use} apartment(s) use it", "danger")
    else:
        db.delete_hub(hub_id)
        flash(f"Deleted hub {hub_id} · {hub['hub_name']}", "success")
    return redirect(url_for("marketing_hubs_page"))


@app.route("/marketing/apartment/<int:apt_id>/edit", methods=["POST"])
@feature_required("apartments", "edit")
def marketing_edit_apartment(apt_id):
    apt = db.get_apartment(apt_id)
    if not apt or apt["deleted"]:
        flash("Apartment not found", "danger")
        return redirect(url_for("marketing_dashboard"))
    name = request.form.get("name", "").strip()
    hub = request.form.get("hub", "").strip()
    link = request.form.get("location_link", "").strip()
    code = request.form.get("apartment_code", "").strip()
    clash = db.get_apartment_by_code(code) if code else None
    if not name or hub not in set(db.hub_names()):
        flash("Apartment name and a valid hub are required", "danger")
    elif clash and clash["id"] != apt_id:
        flash(f"Apartment ID '{code}' is already used", "danger")
    else:
        db.update_apartment(apt_id, name=name, hub=hub, location_link=link, apartment_code=code)
        flash("Apartment updated", "success")
    return redirect(request.form.get("next") or url_for("marketing_dashboard"))


@app.route("/marketing/assign")
@feature_required("assign", "read")
def marketing_assign_page():
    apartments = db.list_apartments()
    return render_template(
        "marketing/assign.html",
        active="assign",
        unassigned=[a for a in apartments if not a["assigned_to"]],
        assigned=[a for a in apartments if a["assigned_to"]],
        btl_users=db.btl_users(),
    )


@app.route("/marketing/assign", methods=["POST"])
@feature_required("assign", "edit")
def marketing_assign():
    ids = request.form.getlist("apartment_ids[]")
    assigned_to = request.form.get("assigned_to", "").strip()
    valid = {u["username"] for u in db.btl_users()}
    if not ids or assigned_to not in valid:
        flash("Select apartments and a BTL user", "danger")
        return redirect(url_for("marketing_assign_page"))
    db.assign_apartments(ids, assigned_to)
    flash(f"Assigned {len(ids)} apartment(s) to {assigned_to}", "success")
    return redirect(url_for("marketing_assign_page"))


@app.route("/marketing/apartment/<int:apt_id>")
@feature_required("apartments", "read")
def marketing_apartment_detail(apt_id):
    apt = db.get_apartment(apt_id)
    if not apt:
        flash("Apartment not found", "danger")
        return redirect(url_for("marketing_dashboard"))
    hubs_by_name = {h["hub_name"]: h["hub_id"] for h in db.list_hubs()}
    return render_template(
        "marketing/apartment_detail.html",
        active="dashboard",
        apt=apt,
        collection=db.get_collection(apt_id),
        hub_names=db.hub_names(),
        hub_id=hubs_by_name.get(apt["hub"]),
    )


@app.route("/marketing/apartment/<int:apt_id>/delete", methods=["POST"])
@feature_required("apartments", "read")
@admin_required
def marketing_delete_apartment(apt_id):
    db.soft_delete_apartment(apt_id)
    flash(f"Apartment #{apt_id} moved to trash", "warning")
    return redirect(url_for("marketing_dashboard"))


@app.route("/marketing/trash")
@feature_required("apartments", "read")
def marketing_trash():
    return render_template(
        "marketing/trash.html", active="trash",
        apartments=db.list_deleted_apartments(),
    )


@app.route("/marketing/apartment/<int:apt_id>/restore", methods=["POST"])
@feature_required("apartments", "edit")
def marketing_restore_apartment(apt_id):
    db.restore_apartment(apt_id)
    flash(f"Apartment #{apt_id} restored", "success")
    return redirect(url_for("marketing_trash"))


@app.route("/marketing/export")
@feature_required("export", "read")
def marketing_export_page():
    return render_template("marketing/export.html", active="export", hub_names=db.hub_names())


@app.route("/marketing/export.xlsx")
@feature_required("export", "read")
def marketing_export_xlsx():
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment
    from openpyxl.utils import get_column_letter

    hub = request.args.get("hub", "").strip()
    status = request.args.get("status", "").strip()

    apartments = db.list_apartments()
    if hub:
        apartments = [a for a in apartments if a["hub"] == hub]
    if status == "Unassigned":
        apartments = [a for a in apartments if not a["assigned_to"]]
    elif status:
        apartments = [a for a in apartments if a["assigned_to"] and a["status"] == status]

    collections = {}
    for a in apartments:
        c = db.get_collection(a["id"])
        if c:
            collections[a["id"]] = c

    wb = Workbook()
    hfill = PatternFill("solid", fgColor="018B9B")
    hfont = Font(bold=True, color="FFFFFF", size=10)

    def style_header(ws, ncols):
        for ci in range(1, ncols + 1):
            c = ws.cell(row=1, column=ci)
            c.font = hfont
            c.fill = hfill
            c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)

    def autosize(ws):
        for col in ws.columns:
            width = max((len(str(c.value)) for c in col if c.value is not None), default=10)
            ws.column_dimensions[get_column_letter(col[0].column)].width = min(width + 3, 48)

    # Sheet 1 — apartments
    ws = wb.active
    ws.title = "Apartments"
    headers = ["ID", "Apartment", "Hub", "Location Link", "Assigned To", "Status",
               "Contact Name", "Contact Number", "Designation", "Total Units", "No-number Reason",
               "Campaigns Available", "Collected By", "Collected At"]
    ws.append(headers)
    for a in apartments:
        c = collections.get(a["id"])
        camps = ""
        if c and c["outcome"] == "number":
            camps = "; ".join(
                f"{x['campaign']} (₹{x['price']:g} × {x['days']}d)" for x in c["campaigns"]
            )
        ws.append([
            a["id"], a["name"], a["hub"], a["location_link"],
            a["assigned_to"] or "—",
            "Unassigned" if not a["assigned_to"] else a["status"],
            (c["contact_name"] if c else "") or "",
            (c["phone"] if c else "") or "",
            (c["designation"] if c else "") or "",
            (c["total_units"] if c else "") or "",
            (c["no_number_reason"] if c else "") or "",
            camps,
            (c["collected_by"] if c else "") or "",
            (c["collected_at"] if c else "") or "",
        ])
    style_header(ws, len(headers))
    autosize(ws)

    # Sheet 2 — campaign line items
    ws2 = wb.create_sheet("Campaigns")
    headers2 = ["Apartment ID", "Apartment", "Hub", "Campaign", "Price (₹)", "Days"]
    ws2.append(headers2)
    apt_by_id = {a["id"]: a for a in apartments}
    for aid, c in collections.items():
        if c["outcome"] != "number":
            continue
        a = apt_by_id[aid]
        for x in c["campaigns"]:
            ws2.append([aid, a["name"], a["hub"], x["campaign"], x["price"], x["days"]])
    style_header(ws2, len(headers2))
    autosize(ws2)

    buf = BytesIO()
    wb.save(buf)
    buf.seek(0)
    return send_file(
        buf, as_attachment=True, download_name="apartment-campaigns.xlsx",
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


@app.route("/marketing/team")
@admin_required
def marketing_team():
    users = db.list_users()
    permissions = {
        u["username"]: db.list_permissions(u["username"])
        for u in users if u["workspace"] == "marketing"
    }
    return render_template(
        "marketing/team.html", active="team",
        users=users, workspace_labels=WORKSPACE_LABELS,
        features=MARKETING_FEATURES, levels=PERMISSION_LEVELS,
        permissions=permissions, default_permission="edit",
    )


@app.route("/marketing/team/add", methods=["POST"])
@admin_required
def marketing_team_add():
    username = request.form.get("username", "").strip().lower()
    name = request.form.get("name", "").strip()
    password = request.form.get("password", "")
    workspace = request.form.get("workspace", "").strip()
    if not username or not password or workspace not in ("marketing", "btl"):
        flash("Username, password and workspace are required", "danger")
    elif db.get_user(username):
        flash(f"Username '{username}' is taken", "danger")
    else:
        db.create_user(username, name or username, hash_password(password), workspace)
        if workspace == "marketing":
            for key in MARKETING_FEATURE_KEYS:
                lvl = request.form.get(f"perm_{key}", "edit")
                if lvl in PERMISSION_LEVELS:
                    db.set_permission(username, key, lvl)
        flash(f"Added {WORKSPACE_LABELS[workspace]} user '{username}'", "success")
    return redirect(url_for("marketing_team"))


@app.route("/marketing/team/<int:user_id>/toggle", methods=["POST"])
@admin_required
def marketing_team_toggle(user_id):
    u = db.get_user_by_id(user_id)
    if not u:
        flash("User not found", "danger")
    elif u["username"] == session["user"]:
        flash("You cannot deactivate your own account", "danger")
    else:
        db.set_user_active(user_id, not u["active"])
        flash(f"{'Activated' if not u['active'] else 'Deactivated'} '{u['username']}'", "success")
    return redirect(url_for("marketing_team"))


@app.route("/marketing/team/<int:user_id>/admin", methods=["POST"])
@admin_required
def marketing_team_admin(user_id):
    u = db.get_user_by_id(user_id)
    if not u:
        flash("User not found", "danger")
    elif u["username"] == session["user"]:
        flash("You can't change your own admin status", "danger")
    elif u["workspace"] != "marketing":
        flash("Only marketing users can be admins", "danger")
    else:
        make_admin = not u.get("is_admin")
        if not make_admin and db.count_admins() <= 1:
            flash("There must be at least one admin", "danger")
        else:
            db.set_user_admin(user_id, make_admin)
            flash(f"{'Granted' if make_admin else 'Removed'} admin for '{u['username']}'", "success")
    return redirect(url_for("marketing_team"))


@app.route("/marketing/team/<int:user_id>/permissions", methods=["POST"])
@admin_required
def marketing_team_permissions(user_id):
    u = db.get_user_by_id(user_id)
    if not u or u["workspace"] != "marketing":
        flash("Marketing user not found", "danger")
        return redirect(url_for("marketing_team"))
    for key in MARKETING_FEATURE_KEYS:
        lvl = request.form.get(f"perm_{key}", "edit")
        db.set_permission(u["username"], key, lvl if lvl in PERMISSION_LEVELS else "edit")
    flash(f"Permissions saved for '{u['username']}'", "success")
    return redirect(url_for("marketing_team"))


@app.route("/marketing/team/<int:user_id>/reset-password", methods=["POST"])
@admin_required
def marketing_team_reset_password(user_id):
    u = db.get_user_by_id(user_id)
    password = request.form.get("password", "")
    if not u or not password:
        flash("A new password is required", "danger")
    else:
        db.set_user_password(user_id, hash_password(password))
        flash(f"Password reset for '{u['username']}'", "success")
    return redirect(url_for("marketing_team"))


# ═══════════════════════════════════════════════════════════════════════════
#  Marketing · Standee tracker
# ═══════════════════════════════════════════════════════════════════════════
@app.route("/marketing/standees")
@feature_required("standees", "read")
def marketing_standees_page():
    standees = db.list_standees()
    stats = db.standee_stats()
    return render_template(
        "marketing/standees.html",
        active="standees",
        standees=standees,
        standees_by_id={s["id"]: s for s in standees},
        stats=stats,
        apartments=db.list_apartments(),
        btl_users=db.btl_users(),
        assignments=db.list_standee_assignments(),
        active_placements=db.active_standee_placements(),
        hub_names=db.hub_names(),
    )


@app.route("/marketing/standees/add", methods=["POST"])
@feature_required("standees", "edit")
def marketing_standee_add():
    name = request.form.get("name", "").strip()
    total = request.form.get("total_units", "0").strip()
    loc = request.form.get("storage_location", "").strip()
    if not name:
        flash("Standee name is required", "danger")
        return redirect(url_for("marketing_standees_page"))
    try:
        total_units = int(total)
    except ValueError:
        total_units = 0
    saved = _save_photos([request.files.get("photo")], "designs")
    standee_id = db.add_standee(name, saved[0] if saved else "", total_units, loc, session["user"])
    if standee_id is None:
        flash(f"Standee '{name}' already exists", "danger")
    else:
        flash(f"Added standee '{name}'", "success")
    return redirect(url_for("marketing_standees_page"))


@app.route("/marketing/standees/<int:standee_id>/reprint", methods=["POST"])
@feature_required("standees", "edit")
def marketing_standee_reprint(standee_id):
    try:
        added = int(request.form.get("added_units", "0"))
    except ValueError:
        added = 0
    note = request.form.get("note", "").strip()
    resolve_damaged = request.form.get("resolve_damaged") == "1"
    if added <= 0:
        flash("Enter a positive number of units", "danger")
    else:
        db.reprint_standee(standee_id, added, note, session["user"], resolve_damaged=resolve_damaged)
        msg = f"Added {added} unit(s)"
        if resolve_damaged:
            msg += " · damaged count updated"
        flash(msg, "success")
    return redirect(url_for("marketing_standees_page"))


@app.route("/marketing/standees/<int:standee_id>/replace", methods=["POST"])
@feature_required("standees", "edit")
def marketing_standee_replace(standee_id):
    old = db.get_standee(standee_id)
    new_name = request.form.get("new_name", "").strip()
    new_total = request.form.get("new_total_units", "0").strip()
    new_storage = request.form.get("new_storage_location", "").strip()
    if not old:
        flash("Standee not found", "danger")
        return redirect(url_for("marketing_standees_page"))
    if not new_name:
        flash("New creative needs a name", "danger")
        return redirect(url_for("marketing_standees_page"))
    try:
        new_total_units = int(new_total)
    except ValueError:
        new_total_units = 0
    saved = _save_photos([request.files.get("new_photo")], "designs")
    new_id = db.add_standee(
        new_name, saved[0] if saved else "", new_total_units,
        new_storage or old["storage_location"], session["user"],
    )
    if new_id is None:
        flash(f"A standee named '{new_name}' already exists", "danger")
        return redirect(url_for("marketing_standees_page"))
    db.retire_standee(standee_id, replaced_by=new_id)
    flash(f"'{old['name']}' retired · new creative '{new_name}' added", "success")
    return redirect(url_for("marketing_standees_page"))


@app.route("/marketing/standees/<int:standee_id>/detail")
@feature_required("standees", "read")
def marketing_standee_detail(standee_id):
    s = db.get_standee(standee_id)
    if not s:
        return {"error": "not found"}, 404
    all_standees = db.list_standees()
    replaced_by = next((x for x in all_standees if x["id"] == s.get("replaced_by")), None)
    replaces = next((x for x in all_standees if x.get("replaced_by") == standee_id), None)
    history = [
        a for a in db.list_standee_assignments() if a["standee_id"] == standee_id
    ]
    s["photo_url"] = f"/static/{s['photo_path']}" if s.get("photo_path") else ""
    s["stats"] = db.standee_stats().get(standee_id, {})
    s["replaced_by_name"] = replaced_by["name"] if replaced_by else None
    s["replaced_by_id"] = replaced_by["id"] if replaced_by else None
    s["replaces_name"] = replaces["name"] if replaces else None
    s["replaces_id"] = replaces["id"] if replaces else None
    s["reprints"] = db.reprint_history(standee_id)
    s["assignments"] = [
        {
            "id": a["id"], "apartment_name": a["apartment_name"], "assigned_to": a["assigned_to"],
            "quantity": a["quantity"], "status": a["status"], "placed_at": a.get("placed_at"),
            "collect_by": a.get("collect_by"), "collected_at": a.get("collected_at"),
            "quantity_returned": a.get("quantity_returned"), "quantity_damaged": a.get("quantity_damaged"),
            "quantity_missing": a.get("quantity_missing"),
        }
        for a in sorted(history, key=lambda x: x["id"], reverse=True)
    ]
    return s


@app.route("/marketing/standees/assign", methods=["POST"])
@feature_required("standees", "edit")
def marketing_standee_assign():
    standee_id = request.form.get("standee_id", "").strip()
    apartment_id = request.form.get("apartment_id", "").strip()
    assigned_to = request.form.get("assigned_to", "").strip()
    quantity = request.form.get("quantity", "").strip()
    duration_days = request.form.get("duration_days", "").strip()
    valid_btl = {u["username"] for u in db.btl_users()}
    if not all([standee_id, apartment_id, assigned_to, quantity, duration_days]) or assigned_to not in valid_btl:
        flash("Standee, apartment, BTL coordinator, quantity and duration are all required", "danger")
        return redirect(url_for("marketing_standees_page"))
    try:
        qty, days = int(quantity), int(duration_days)
    except ValueError:
        flash("Quantity and duration must be numbers", "danger")
        return redirect(url_for("marketing_standees_page"))
    loc = _resolve_location_pair("collection_location", "collection_location_detail")
    db.create_standee_assignment(standee_id, apartment_id, assigned_to, qty, days, loc, session["user"])
    flash("Standee assigned", "success")
    return redirect(url_for("marketing_standees_page"))


@app.route("/marketing/standees/assignment/<int:assignment_id>")
@feature_required("standees", "read")
def marketing_standee_assignment_detail(assignment_id):
    a = db.get_standee_assignment(assignment_id)
    if not a:
        return {"error": "not found"}, 404
    a["photos"] = [
        {"kind": p["kind"], "url": f"/static/{p['path']}", "uploaded_at": p["uploaded_at"]}
        for p in db.photos_for(assignment_id)
    ]
    return a


# ═══════════════════════════════════════════════════════════════════════════
#  BTL
# ═══════════════════════════════════════════════════════════════════════════
@app.route("/btl")
@role_required("btl")
def btl_dashboard():
    apartments = db.list_apartments_for_btl(session["user"])
    collections = db.collections_by_apartment()
    return render_template(
        "btl/dashboard.html",
        active="dashboard",
        apartments=apartments,
        collections=collections,
        counts={
            "all": len(apartments),
            STATUS_PENDING: len([a for a in apartments if a["status"] == STATUS_PENDING]),
            STATUS_COLLECTED: len([a for a in apartments if a["status"] == STATUS_COLLECTED]),
            STATUS_NO_NUMBER: len([a for a in apartments if a["status"] == STATUS_NO_NUMBER]),
        },
    )


@app.route("/btl/apartment/<int:apt_id>")
@role_required("btl")
def btl_collection_form(apt_id):
    apt = db.get_apartment(apt_id)
    if not apt or apt["deleted"] or apt["assigned_to"] != session["user"]:
        flash("That apartment is not assigned to you", "danger")
        return redirect(url_for("btl_dashboard"))
    return render_template(
        "btl/collection_form.html",
        apt=apt,
        collection=db.get_collection(apt_id),
        campaigns=MARKETING_CAMPAIGNS,
        designations=DESIGNATIONS,
    )


@app.route("/btl/apartment/<int:apt_id>/collect", methods=["POST"])
@role_required("btl")
def btl_collect(apt_id):
    apt = db.get_apartment(apt_id)
    if not apt or apt["deleted"] or apt["assigned_to"] != session["user"]:
        flash("That apartment is not assigned to you", "danger")
        return redirect(url_for("btl_dashboard"))

    number_available = request.form.get("number_available") == "yes"

    if number_available:
        contact_name = request.form.get("contact_name", "").strip()
        phone = request.form.get("phone", "").strip()
        designation = request.form.get("designation", "").strip()
        try:
            total_units = int(request.form.get("total_units", "0") or 0)
        except ValueError:
            total_units = 0
        if not phone:
            flash("Contact number is required", "danger")
            return redirect(url_for("btl_collection_form", apt_id=apt_id))
        if designation not in DESIGNATIONS:
            flash("Select a valid designation", "danger")
            return redirect(url_for("btl_collection_form", apt_id=apt_id))
        db.save_collection(
            apt_id, "number", contact_name, phone, designation, total_units, "",
            _campaigns_from_form(), session["user"],
        )
        flash("Collection saved", "success")
    else:
        reason = request.form.get("no_number_reason", "").strip()
        db.save_collection(apt_id, "no_number", "", "", "", 0, reason, [], session["user"])
        flash("Marked as no number available", "success")

    return redirect(url_for("btl_dashboard"))


# ═══════════════════════════════════════════════════════════════════════════
#  BTL · Standee tracker
# ═══════════════════════════════════════════════════════════════════════════
@app.route("/btl/standees")
@role_required("btl")
def btl_standees_page():
    assignments = db.list_standee_assignments_for_btl(session["user"])
    return render_template(
        "btl/standees.html",
        active="standees",
        assignments=assignments,
        today=date.today().isoformat(),
        counts={
            "all": len(assignments),
            "Assigned": len([a for a in assignments if a["status"] == "Assigned"]),
            "Placed": len([a for a in assignments if a["status"] == "Placed"]),
            "Collected": len([a for a in assignments if a["status"] == "Collected"]),
        },
    )


@app.route("/btl/standees/<int:assignment_id>")
@role_required("btl")
def btl_standee_detail(assignment_id):
    a = db.get_standee_assignment(assignment_id)
    if not a or a["assigned_to"] != session["user"]:
        flash("That task is not assigned to you", "danger")
        return redirect(url_for("btl_standees_page"))
    pending = [
        x for x in db.list_standee_assignments_for_btl(session["user"])
        if x["status"] == "Assigned" and x["id"] != assignment_id
    ]
    return render_template(
        "btl/standee_detail.html",
        a=a,
        collection=db.get_collection(a["apartment_id"]),
        photos=db.photos_for(assignment_id),
        hub_names=db.hub_names(),
        pending_assignments=pending,
    )


@app.route("/btl/standees/<int:assignment_id>/place", methods=["POST"])
@role_required("btl")
def btl_standee_place(assignment_id):
    a = db.get_standee_assignment(assignment_id)
    if not a or a["assigned_to"] != session["user"] or a["status"] != "Assigned":
        flash("This task can't be placed right now", "danger")
        return redirect(url_for("btl_standees_page"))
    saved = _save_photos(request.files.getlist("photos"), assignment_id)
    if not saved:
        flash("Add at least one photo to confirm placement", "danger")
        return redirect(url_for("btl_standee_detail", assignment_id=assignment_id))
    db.confirm_placement(assignment_id, session["user"], saved)
    flash("Placement confirmed", "success")
    return redirect(url_for("btl_standees_page"))


@app.route("/btl/standees/<int:assignment_id>/collect", methods=["POST"])
@role_required("btl")
def btl_standee_collect(assignment_id):
    a = db.get_standee_assignment(assignment_id)
    if not a or a["assigned_to"] != session["user"] or a["status"] != "Placed":
        flash("This task can't be collected right now", "danger")
        return redirect(url_for("btl_standees_page"))
    qty = int(a["quantity"] or 0)

    def _int(name, default=0):
        try:
            return int(request.form.get(name, str(default)) or default)
        except ValueError:
            return default

    returned = max(0, min(qty, _int("quantity_returned")))

    damaged = 0
    if request.form.get("damaged_flag") == "yes":
        damaged = min(max(1, _int("quantity_damaged", 1)), max(0, qty - returned))
    missing = 0
    if request.form.get("missing_flag") == "yes":
        missing = min(max(1, _int("quantity_missing", 1)), max(0, qty - returned - damaged))
    note = request.form.get("damage_note", "").strip() if damaged else ""

    # where it goes next: a hub, or redeployed to one of my pending assignments
    drop_type = request.form.get("drop_type", "hub")
    redeploy_id, dest = None, None
    if drop_type == "assignment":
        rid = _int("drop_assignment_id")
        dest = db.get_standee_assignment(rid) if rid else None
        if not dest or dest["assigned_to"] != session["user"] or dest["status"] != "Assigned":
            flash("Pick a valid pending assignment to redeploy to", "danger")
            return redirect(url_for("btl_standee_detail", assignment_id=assignment_id))
        redeploy_id = rid
        loc = f"→ {dest['standee_name']} @ {dest['apartment_name']}"
    else:
        loc = request.form.get("drop_hub", "").strip() or a["apartment_hub"]

    saved = _save_photos(request.files.getlist("damage_photos"), assignment_id) if damaged else []
    db.collect_standee_assignment(
        assignment_id, returned, damaged, note, loc, session["user"], saved,
        quantity_missing=missing, redeployed_to=redeploy_id,
    )
    if redeploy_id:
        db.confirm_placement(redeploy_id, session["user"], [])
        flash(f"Collected · redeployed to {dest['apartment_name']} ({dest['standee_name']})", "success")
    else:
        flash("Standee collected", "success")
    return redirect(url_for("btl_standees_page"))


# ── errors ───────────────────────────────────────────────────────────────
@app.errorhandler(404)
def not_found(e):
    return render_template("error.html", code=404,
                           message="That page doesn't exist."), 404


@app.errorhandler(500)
def server_error(e):
    return render_template("error.html", code=500,
                           message="Something went wrong. Please try again."), 500


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print(f"\n  → http://127.0.0.1:{port}\n")
    app.run(host="0.0.0.0", port=port, debug=True)
