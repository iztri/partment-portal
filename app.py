"""
Apartment Detail Portal — Flask Web App
Run:  python app.py
Then: Open http://<your-ip>:5000 on phone/laptop
"""

import json
from flask import Flask, render_template, request, redirect, url_for, session, flash
from auth import login_required, role_required, authenticate, logout
from sheets_db import SheetsDB
from config import USERS, MARKETING_CHANNELS, HUB_NAMES

app = Flask(__name__)
app.secret_key = "apartment-portal-secret-key-2024"  # Change in production

@app.template_filter("from_json")
def from_json_filter(value):
    if isinstance(value, str):
        try:
            return json.loads(value)
        except:
            return []
    return value if isinstance(value, list) else []

db = SheetsDB()


# ── Auth Routes ───────────────────────────────────────────────────────────
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()
        if authenticate(username, password):
            flash(f"Welcome, {session.get('name')}!", "success")
            if session["role"] == "marketing":
                return redirect(url_for("marketing_dashboard"))
            return redirect(url_for("field_dashboard"))
        flash("Invalid username or password", "danger")
    return render_template("login.html")


@app.route("/logout")
def app_logout():
    logout()
    return redirect(url_for("login"))


# ── Marketing Team Routes ─────────────────────────────────────────────────
@app.route("/marketing")
@login_required
@role_required("marketing")
def marketing_dashboard():
    apartments = db.get_all_apartments()
    apartments.reverse()

    # Build latest visit date per apartment
    all_visits = db.get_visits()
    visit_map = {}
    for v in all_visits:
        aid = str(v.get("Apartment ID", ""))
        if aid not in visit_map:
            visit_map[aid] = v
    for apt in apartments:
        aid = str(apt.get("Apartment ID", ""))
        v = visit_map.get(aid)
        apt["_visited_at"] = v["Visited At"] if v else ""
        apt["_visited_by"] = v["Visited By"] if v else ""

    field_users = [
        {"username": u, "name": info["name"]}
        for u, info in USERS.items() if info["role"] == "field"
    ]
    return render_template(
        "marketing_dashboard.html",
        apartments=apartments,
        field_users=field_users,
        marketing_channels=MARKETING_CHANNELS,
        hub_names=HUB_NAMES,
    )


@app.route("/marketing/add", methods=["POST"])
@login_required
@role_required("marketing")
def add_apartment():
    name = request.form.get("apartment_name", "").strip()
    hub = request.form.get("hub_name", "").strip()
    link = request.form.get("location_link", "").strip()
    if not name or not hub:
        flash("Apartment name and Hub name are required", "danger")
        return redirect(url_for("marketing_dashboard"))
    db.add_apartment(name, hub, link, session.get("user"))
    flash(f"Apartment '{name}' added!", "success")
    return redirect(url_for("marketing_dashboard"))


@app.route("/marketing/assign", methods=["POST"])
@login_required
@role_required("marketing")
def assign_apartments():
    apartment_ids = request.form.getlist("apartment_ids[]")
    assigned_to = request.form.get("assigned_to", "").strip()
    assigned_date = request.form.get("assigned_date", "").strip()
    if not apartment_ids or not assigned_to or not assigned_date:
        flash("Select apartments, field user, and date", "danger")
        return redirect(url_for("marketing_dashboard"))
    db.assign_apartments(apartment_ids, assigned_to, assigned_date)
    flash(f"Assigned {len(apartment_ids)} apartment(s) to {assigned_to}", "success")
    return redirect(url_for("marketing_dashboard"))


@app.route("/marketing/edit/<int:apartment_id>", methods=["POST"])
@login_required
@role_required("marketing")
def edit_apartment(apartment_id):
    name = request.form.get("apartment_name", "").strip()
    hub = request.form.get("hub_name", "").strip()
    link = request.form.get("location_link", "").strip()
    assigned_to = request.form.get("assigned_to", "").strip()
    assigned_date = request.form.get("assigned_date", "").strip()

    updates = {}
    if name:
        updates["Apartment Name"] = name
    if hub:
        updates["Hub Name"] = hub
    if link:
        updates["Location Link"] = link

    # Reassignment resets status to Pending
    if assigned_to or assigned_date:
        # Fetch current record to detect changes
        all_apts = db.get_all_apartments()
        current = next((a for a in all_apts if str(a.get("Apartment ID")) == str(apartment_id)), None)
        old_user = (current or {}).get("Assigned To", "")
        old_date = (current or {}).get("Assigned Date", "")
        if assigned_to and assigned_to != old_user:
            updates["Assigned To"] = assigned_to
        if assigned_date and assigned_date != old_date:
            updates["Assigned Date"] = assigned_date
        if "Assigned To" in updates or "Assigned Date" in updates:
            updates["Status"] = "Pending"
            db.update_apartment(apartment_id, **updates)
            flash(f"Apartment reassigned & reset to Pending ✓", "success")
        else:
            if updates:
                db.update_apartment(apartment_id, **updates)
                flash("Apartment updated!", "success")
            else:
                flash("No changes made", "info")
    else:
        if updates:
            db.update_apartment(apartment_id, **updates)
            flash("Apartment updated!", "success")
        else:
            flash("No changes made", "info")
    return redirect(url_for("marketing_dashboard"))


# ── Field Team Routes ─────────────────────────────────────────────────────
@app.route("/field")
@login_required
@role_required("field")
def field_dashboard():
    username = session.get("user")
    selected_date = request.args.get("date", "")
    apartments = db.get_assigned_for_user(username, selected_date) if selected_date else []
    available_dates = db.get_available_dates_for_user(username)
    return render_template(
        "field_dashboard.html",
        apartments=apartments,
        available_dates=available_dates,
        selected_date=selected_date,
        marketing_channels=MARKETING_CHANNELS,
    )


def _channel_key(ch):
    cleaned = ch.replace(' ', '_').replace('/', '_').replace('(', '').replace(')', '').replace("'", '').replace('.', '')
    return f"ch_{cleaned}"

@app.route("/field/visit/<int:apartment_id>")
@login_required
@role_required("field")
def visit_form(apartment_id):
    apartments = db.get_all_apartments()
    apt = None
    for a in apartments:
        if int(a.get("Apartment ID", 0)) == apartment_id:
            apt = a
            break
    if not apt:
        flash("Apartment not found", "danger")
        return redirect(url_for("field_dashboard"))
    visits = db.get_visits(apartment_id)
    latest_visit = visits[-1] if visits else None
    existing_data = {}
    if latest_visit and latest_visit.get("Channels Data (JSON)"):
        try:
            channels_list = json.loads(latest_visit["Channels Data (JSON)"])
            existing_data["channels"] = {c["channel"]: c for c in channels_list}
        except:
            existing_data["channels"] = {}
        existing_data["manager_name"] = latest_visit.get("Manager Name", "")
        existing_data["no_of_units"] = latest_visit.get("No of Units", "")
        existing_data["manager_phone"] = latest_visit.get("Manager Phone", "")
        existing_data["notes"] = latest_visit.get("Notes", "")
    return render_template(
        "visit_form.html",
        apartment=apt,
        marketing_channels=MARKETING_CHANNELS,
        existing_data=existing_data,
    )


@app.route("/field/submit-visit", methods=["POST"])
@login_required
@role_required("field")
def submit_visit():
    apartment_id = request.form.get("apartment_id")
    apartment_name = request.form.get("apartment_name", "")
    hub_name = request.form.get("hub_name", "")
    manager_name = request.form.get("manager_name", "").strip()
    no_of_units = request.form.get("no_of_units", "0").strip()
    manager_phone = request.form.get("manager_phone", "").strip()
    notes = request.form.get("notes", "").strip()

    if not manager_name:
        flash("Manager name is required", "danger")
        return redirect(url_for("visit_form", apartment_id=apartment_id))

    # Build channels data from form
    channels_data = []
    for ch in MARKETING_CHANNELS:
        key = _channel_key(ch)
        available = request.form.get(f"{key}_available") == "on"
        amount = request.form.get(f"{key}_amount", "0").strip()
        days = request.form.get(f"{key}_days", "0").strip()
        if available:
            channels_data.append({
                "channel": ch,
                "available": True,
                "amount": int(amount) if amount else 0,
                "days": int(days) if days else 0,
            })

    db.record_visit(
        apartment_id=apartment_id,
        apartment_name=apartment_name,
        hub_name=hub_name,
        manager_name=manager_name,
        no_of_units=int(no_of_units) if no_of_units else 0,
        manager_phone=manager_phone,
        channels_data=channels_data,
        notes=notes,
        visited_by=session.get("user"),
    )
    flash(f"Visit recorded for {apartment_name}!", "success")
    return redirect(url_for("field_dashboard"))


# ── View Visit Details (both roles) ──────────────────────────────────────
@app.route("/visit/<int:apartment_id>")
@login_required
def view_visit(apartment_id):
    visits = db.get_visits(apartment_id)
    return render_template("view_visit.html", visits=visits, apartment_id=apartment_id)


# ── Home ──────────────────────────────────────────────────────────────────
@app.route("/")
def home():
    if "user" in session:
        if session["role"] == "marketing":
            return redirect(url_for("marketing_dashboard"))
        return redirect(url_for("field_dashboard"))
    return redirect(url_for("login"))


# ── Run ───────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 5000))
    print(f"\n  → Server starting on http://0.0.0.0:{port}")
    print(f"  → Other devices on your network use: http://<YOUR-IP>:{port}")
    print(f"  → Press Ctrl+C to stop\n")
    app.run(host="0.0.0.0", port=port, debug=True)
