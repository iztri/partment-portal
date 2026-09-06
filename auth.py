"""Session authentication + Marketing-workspace access control, backed by the
``users`` and ``user_permissions`` tables."""

import os
from functools import wraps

from flask import session, redirect, url_for, request, render_template, g
from werkzeug.security import check_password_hash
from werkzeug.security import generate_password_hash as _gph

from db import get_db
from config import MARKETING_FEATURE_KEYS, PERMISSION_RANK, DEFAULT_PERMISSION

# scrypt (werkzeug's default) needs OpenSSL 1.1+; not available on this Python's
# LibreSSL build, so pin PBKDF2.
def hash_password(password):
    return _gph(password, method="pbkdf2:sha256")


# ── request-scoped caches ───────────────────────────────────────────────
def _cached_user(username):
    if not username:
        return None
    cache = getattr(g, "_user_cache", None)
    if cache is None:
        cache = g._user_cache = {}
    if username not in cache:
        try:
            cache[username] = get_db().get_user(username)
        except Exception:
            cache[username] = None
    return cache[username]


def is_admin_user(username):
    u = _cached_user(username)
    return bool(u and u.get("is_admin"))


def effective_level(username, feature):
    """'none' | 'read' | 'edit' for a marketing user on one feature.
    Admins are always 'edit'. Marketing users with no explicit row default to
    'edit' so existing accounts keep working. Non-marketing users get 'none'."""
    u = _cached_user(username)
    if not u or u.get("workspace") != "marketing":
        return "none"
    if u.get("is_admin"):
        return "edit"
    cache = getattr(g, "_perm_cache", None)
    if cache is None:
        cache = g._perm_cache = {}
    if username not in cache:
        try:
            cache[username] = get_db().list_permissions(username) or {}
        except Exception:
            cache[username] = {}
    return cache[username].get(feature, DEFAULT_PERMISSION)


def has_level(username, feature, need="read"):
    return PERMISSION_RANK.get(effective_level(username, feature), 0) >= PERMISSION_RANK.get(need, 0)


# ── decorators ──────────────────────────────────────────────────────────
def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if "user" not in session:
            return redirect(url_for("login", next=request.path))
        return f(*args, **kwargs)
    return wrapper


def role_required(*roles):
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            if "user" not in session:
                return redirect(url_for("login", next=request.path))
            if session.get("role") not in roles:
                return render_template(
                    "error.html", code=403,
                    message="This page belongs to the other workspace.",
                ), 403
            return f(*args, **kwargs)
        return wrapper
    return decorator


def admin_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if "user" not in session:
            return redirect(url_for("login", next=request.path))
        if not is_admin_user(session.get("user")):
            return render_template(
                "error.html", code=403, message="This action is restricted to admins.",
            ), 403
        return f(*args, **kwargs)
    return wrapper


def feature_required(feature, need="read"):
    """Guard a marketing route by the caller's level on `feature` ('read' or 'edit')."""
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            if "user" not in session:
                return redirect(url_for("login", next=request.path))
            if session.get("role") != "marketing":
                return render_template(
                    "error.html", code=403,
                    message="This page belongs to the other workspace.",
                ), 403
            level = effective_level(session["user"], feature)
            if PERMISSION_RANK.get(level, 0) < PERMISSION_RANK.get(need, 0):
                message = (
                    "You don't have access to this section — ask an admin."
                    if level == "none"
                    else "You have read-only access to this section."
                )
                return render_template("error.html", code=403, message=message), 403
            return f(*args, **kwargs)
        return wrapper
    return decorator


# ── session lifecycle ───────────────────────────────────────────────────
def authenticate(username, password):
    user = get_db().get_user(username.strip())
    if not user or not user.get("active"):
        return False
    if not check_password_hash(user["password_hash"], password):
        return False
    session["user"] = user["username"]
    session["role"] = user["workspace"]
    session["name"] = user["name"] or user["username"]
    session["is_admin"] = bool(user.get("is_admin"))
    return True


def logout():
    session.clear()


def ensure_seed_admin():
    """Create the first marketing admin if the users table is empty."""
    db = get_db()
    if db.count_users() > 0:
        return
    username = os.environ.get("ADMIN_USERNAME", "gowtham").strip() or "gowtham"
    password = os.environ.get("ADMIN_PASSWORD", "iztri@123")
    uid = db.create_user(username, "Gowtham", hash_password(password), "marketing")
    if uid is not None:
        db.set_user_admin(uid, True)
    print(f"  → Seeded marketing admin '{username}'.")
