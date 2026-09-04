"""Session authentication, backed by the ``users`` table."""

import os
from functools import wraps

from flask import session, redirect, url_for, request, render_template
from werkzeug.security import check_password_hash
from werkzeug.security import generate_password_hash as _gph

from db import get_db

# scrypt (werkzeug's default) needs OpenSSL 1.1+; not available on this Python's
# LibreSSL build, so pin PBKDF2.
def hash_password(password):
    return _gph(password, method="pbkdf2:sha256")


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


def authenticate(username, password):
    user = get_db().get_user(username.strip())
    if not user or not user.get("active"):
        return False
    if not check_password_hash(user["password_hash"], password):
        return False
    session["user"] = user["username"]
    session["role"] = user["workspace"]
    session["name"] = user["name"] or user["username"]
    return True


def logout():
    session.clear()


def ensure_seed_admin():
    """Create the first marketing admin if the users table is empty."""
    db = get_db()
    if db.count_users() > 0:
        return
    username = os.environ.get("ADMIN_USERNAME", "admin").strip() or "admin"
    password = os.environ.get("ADMIN_PASSWORD", "admin123")
    db.create_user(username, "Admin", hash_password(password), "marketing")
    print(f"  → Seeded marketing admin '{username}'. "
          f"{'CHANGE THE DEFAULT PASSWORD.' if password == 'admin123' else ''}")
