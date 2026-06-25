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
    "marketing1": {"password": "mark@123", "role": "marketing", "name": "Marketing Lead"},
    "rohit":      {"password": "rohit@123", "role": "marketing", "name": "Rohit - Marketing"},
    "field1":     {"password": "field@123", "role": "field", "name": "Rahul - Field"},
    "field2":     {"password": "field@123", "role": "field", "name": "Suresh - Field"},
    "field3":     {"password": "field@123", "role": "field", "name": "Amit - Field"},
    "field4":     {"password": "field@123", "role": "field", "name": "Vijay - Field"},
    "field5":     {"password": "field@123", "role": "field", "name": "Deepak - Field"},
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
