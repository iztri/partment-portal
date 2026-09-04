"""Marketing + BTL apartment campaign portal.

Run locally:  PORT=5055 python3 app.py
"""

import os
from io import BytesIO

from flask import (
    Flask, render_template, request, redirect, url_for, session, flash, send_file
)
from auth import (
    login_required, role_required, authenticate, logout, ensure_seed_admin, hash_password,
)
from db import get_db
from config import (
    HUB_NAMES, MARKETING_CAMPAIGNS, DESIGNATIONS, WORKSPACE_LABELS,
    STATUS_PENDING, STATUS_COLLECTED, STATUS_NO_NUMBER,
)

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET", "dev-only-change-me")

db = get_db()
ensure_seed_admin()


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
    return redirect(url_for("marketing_dashboard" if session["role"] == "marketing" else "btl_dashboard"))


# ═══════════════════════════════════════════════════════════════════════════
#  Marketing
# ═══════════════════════════════════════════════════════════════════════════
@app.route("/marketing")
@role_required("marketing")
def marketing_dashboard():
    apartments = db.list_apartments()
    collections = db.collections_by_apartment()
    return render_template(
        "marketing/dashboard.html",
        active="dashboard",
        apartments=apartments,
        collections=collections,
        stats=_apartment_stats(apartments),
        hub_names=HUB_NAMES,
    )


@app.route("/marketing/add")
@role_required("marketing")
def marketing_add_page():
    return render_template("marketing/add.html", active="add", hub_names=HUB_NAMES)


@app.route("/marketing/add", methods=["POST"])
@role_required("marketing")
def marketing_add():
    name = request.form.get("name", "").strip()
    hub = request.form.get("hub", "").strip()
    link = request.form.get("location_link", "").strip()
    if not name or hub not in HUB_NAMES:
        flash("Apartment name and a valid hub are required", "danger")
        return redirect(url_for("marketing_add_page"))
    db.add_apartment(name, hub, link, session["user"])
    flash(f"Added '{name}'", "success")
    return redirect(url_for("marketing_add_page"))


@app.route("/marketing/bulk-upload", methods=["POST"])
@role_required("marketing")
def marketing_bulk_upload():
    raw = request.form.get("bulk_data", "").strip()
    if not raw:
        flash("Nothing to upload", "danger")
        return redirect(url_for("marketing_add_page"))
    rows, errors = [], []
    for i, line in enumerate((l for l in raw.splitlines() if l.strip()), 1):
        parts = [p.strip() for p in line.split(",")]
        name = parts[0] if parts else ""
        hub = parts[1] if len(parts) > 1 else ""
        link = parts[2] if len(parts) > 2 else ""
        if not name or hub not in HUB_NAMES:
            errors.append(f"Row {i}: '{line}'")
            continue
        rows.append((name, hub, link))
    if rows:
        db.bulk_add_apartments(rows, session["user"])
    msg = f"Added {len(rows)} apartment(s)"
    if errors:
        msg += f" · skipped {len(errors)} (bad name/hub): " + "; ".join(errors[:3])
    flash(msg, "success" if rows and not errors else "warning")
    return redirect(url_for("marketing_add_page"))


@app.route("/marketing/apartment/<int:apt_id>/edit", methods=["POST"])
@role_required("marketing")
def marketing_edit_apartment(apt_id):
    apt = db.get_apartment(apt_id)
    if not apt or apt["deleted"]:
        flash("Apartment not found", "danger")
        return redirect(url_for("marketing_dashboard"))
    name = request.form.get("name", "").strip()
    hub = request.form.get("hub", "").strip()
    link = request.form.get("location_link", "").strip()
    if not name or hub not in HUB_NAMES:
        flash("Apartment name and a valid hub are required", "danger")
    else:
        db.update_apartment(apt_id, name=name, hub=hub, location_link=link)
        flash("Apartment updated", "success")
    return redirect(request.form.get("next") or url_for("marketing_dashboard"))


@app.route("/marketing/assign")
@role_required("marketing")
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
@role_required("marketing")
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
@role_required("marketing")
def marketing_apartment_detail(apt_id):
    apt = db.get_apartment(apt_id)
    if not apt:
        flash("Apartment not found", "danger")
        return redirect(url_for("marketing_dashboard"))
    return render_template(
        "marketing/apartment_detail.html",
        active="dashboard",
        apt=apt,
        collection=db.get_collection(apt_id),
        hub_names=HUB_NAMES,
    )


@app.route("/marketing/apartment/<int:apt_id>/delete", methods=["POST"])
@role_required("marketing")
def marketing_delete_apartment(apt_id):
    db.soft_delete_apartment(apt_id)
    flash(f"Apartment #{apt_id} moved to trash", "warning")
    return redirect(url_for("marketing_dashboard"))


@app.route("/marketing/trash")
@role_required("marketing")
def marketing_trash():
    return render_template(
        "marketing/trash.html", active="trash",
        apartments=db.list_deleted_apartments(),
    )


@app.route("/marketing/apartment/<int:apt_id>/restore", methods=["POST"])
@role_required("marketing")
def marketing_restore_apartment(apt_id):
    db.restore_apartment(apt_id)
    flash(f"Apartment #{apt_id} restored", "success")
    return redirect(url_for("marketing_trash"))


@app.route("/marketing/export")
@role_required("marketing")
def marketing_export_page():
    return render_template("marketing/export.html", active="export", hub_names=HUB_NAMES)


@app.route("/marketing/export.xlsx")
@role_required("marketing")
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
               "Contact Number", "Designation", "No-number Reason",
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
            (c["phone"] if c else "") or "",
            (c["designation"] if c else "") or "",
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
@role_required("marketing")
def marketing_team():
    return render_template(
        "marketing/team.html", active="team",
        users=db.list_users(), workspace_labels=WORKSPACE_LABELS,
    )


@app.route("/marketing/team/add", methods=["POST"])
@role_required("marketing")
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
        flash(f"Added {WORKSPACE_LABELS[workspace]} user '{username}'", "success")
    return redirect(url_for("marketing_team"))


@app.route("/marketing/team/<int:user_id>/toggle", methods=["POST"])
@role_required("marketing")
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


@app.route("/marketing/team/<int:user_id>/reset-password", methods=["POST"])
@role_required("marketing")
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
        phone = request.form.get("phone", "").strip()
        designation = request.form.get("designation", "").strip()
        if not phone:
            flash("Contact number is required", "danger")
            return redirect(url_for("btl_collection_form", apt_id=apt_id))
        if designation not in DESIGNATIONS:
            flash("Select a valid designation", "danger")
            return redirect(url_for("btl_collection_form", apt_id=apt_id))
        db.save_collection(
            apt_id, "number", phone, designation, "",
            _campaigns_from_form(), session["user"],
        )
        flash("Collection saved", "success")
    else:
        reason = request.form.get("no_number_reason", "").strip()
        db.save_collection(apt_id, "no_number", "", "", reason, [], session["user"])
        flash("Marked as no number available", "success")

    return redirect(url_for("btl_dashboard"))


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
