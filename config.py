"""
Configuration file for Apartment Detail Portal.
Edit the USERS dict and Supabase credentials before running.
"""

import os

# ── Supabase ─────────────────────────────────────────────────────────────
SUPABASE_URL = "https://ppxyhlmlymvhrjdcnoks.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InBweHlobG1seW12aHJqZGNub2tzIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc4MjM2MzY1NCwiZXhwIjoyMDk3OTM5NjU0fQ.D7QZbfzpZKtutgo4lp4F8R15HNlzQAf7N3ApBz6GQ6s"

# ── User Authentication ───────────────────────────────────────────────────
# Format: "username": {"password": "...", "role": "marketing" or "field", "name": "..."}
USERS = {
    "rohit":  {"password": "rohit@123",  "role": "marketing", "name": "Rohit - Marketing"},
    "deva":   {"password": "deva@123",   "role": "marketing", "name": "Deva - Marketing"},
    "gowtham": {"password": "iztri@123", "role": "marketing", "name": "Gowtham - Marketing"},
    "akshay": {"password": "akshay@123", "role": "field",     "name": "Akshay - Field"},
}

# ── Marketing Channels (checkboxes in visit form) ─────────────────────────
MARKETING_CHANNELS = [
    "WhatsApp Burst", "MyGate Burst", "Banner", "Standee",
    "Physical Flyers", "Notice Board", "Lift Marketing",
    "Newspaper", "Bill Boards", "Parking Banner",
    "Google Ad", "Meta Ad",
    "POST BOX", "Website (Apartment's)", "Stalls", "Telegram",
]

# ── Hub Names ─────────────────────────────────────────────────────────────
HUB_NAMES = [
    "Arekere", "Brigade Meadows", "Brigade Omega", "Brigade Panorama",
    "Elita Promenade", "Godrej E-city", "House of Hiranandani",
    "Koramangala", "Nandi Citadel", "Prestige Jindal City",
    "Prestige Sunrise Park", "Sattva Misty Charm", "Valmark CityVille",
]

# ── Supabase Table Names ───────────────────────────────────────────────────
SHEET_TABS = {
    "apartments": "apartments",
    "visits": "visits",
}
