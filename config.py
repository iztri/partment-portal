"""Static configuration for the Marketing + BTL portal.

No secrets live here. Runtime secrets come from environment variables:
  FLASK_SECRET      - session signing key
  DATABASE_BACKEND  - "supabase" to use Supabase, anything else uses local SQLite
                      (also switched on automatically when RENDER is set)
  SUPABASE_URL      - Supabase project URL      (prod only)
  SUPABASE_KEY      - Supabase service_role key (prod only)
  ADMIN_USERNAME    - seeded marketing admin username (first run only, default "admin")
  ADMIN_PASSWORD    - seeded marketing admin password (first run only, default "admin123")
"""

# ── Workspaces / roles ───────────────────────────────────────────────────
WORKSPACES = ["marketing", "btl"]
WORKSPACE_LABELS = {"marketing": "Marketing", "btl": "BTL"}

# ── Contact designations (BTL collection form) ────────────────────────────
DESIGNATIONS = ["Security", "Apartment Manager", "Association Member"]

# ── Marketing campaigns (BTL marks which are available + price/days) ──────
MARKETING_CAMPAIGNS = [
    "WhatsApp Burst", "MyGate Burst", "Banner", "Standee",
    "Physical Flyers", "Notice Board", "Lift Marketing",
    "Newspaper", "Bill Boards", "Parking Banner",
    "Google Ad", "Meta Ad",
    "POST BOX", "Website (Apartment's)", "Stalls", "Telegram",
]

# ── Hubs (apartment grouping) ────────────────────────────────────────────
# Master list lives in the `hubs` DB table (managed under Marketing › Hubs).
# This is only the first-run seed — (hub_id, hub_name), IDs come from the
# marketing team's own numbering, not necessarily sequential.
HUBS_SEED = [
    (1, "Arekere"),
    (8, "Elita Promenade"),
    (9, "Nandi Citadel"),
    (12, "Godrej E-city"),
    (11, "Sattva Misty Charm"),
    (28, "Prestige Jindal City"),
    (20, "Brigade Panorama"),
    (31, "House of Hiranandani"),
    (32, "Koramangala"),
    (33, "Electronic City"),
    (34, "Sobha Dream Acres"),
    (37, "Adarsh Palm Retreat"),
]
# Fallback name list (used only if the hubs table can't be read).
HUB_NAMES = [name for _, name in HUBS_SEED]

# ── Apartment status values ─────────────────────────────────────────────
STATUS_PENDING = "Pending"
STATUS_COLLECTED = "Collected"
STATUS_NO_NUMBER = "No Number"
