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

# ── Hubs (fixed apartment grouping) ──────────────────────────────────────
HUB_NAMES = [
    "Arekere", "Brigade Meadows", "Brigade Omega", "Brigade Panorama",
    "Elita Promenade", "Godrej E-city", "House of Hiranandani",
    "Koramangala", "Nandi Citadel", "Prestige Jindal City",
    "Prestige Sunrise Park", "Sattva Misty Charm", "Valmark CityVille",
]

# ── Apartment status values ─────────────────────────────────────────────
STATUS_PENDING = "Pending"
STATUS_COLLECTED = "Collected"
STATUS_NO_NUMBER = "No Number"
