"""Simple authentication using Flask sessions."""

from functools import wraps
from flask import session, redirect, url_for, request
from config import USERS


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user" not in session:
            return redirect(url_for("login", next=request.url))
        return f(*args, **kwargs)
    return decorated


def role_required(*roles):
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            if session.get("role") not in roles:
                return "Access denied", 403
            return f(*args, **kwargs)
        return decorated
    return decorator


def authenticate(username, password):
    if username in USERS and USERS[username]["password"] == password:
        session["user"] = username
        session["role"] = USERS[username]["role"]
        session["name"] = USERS[username]["name"]
        return True
    return False


def logout():
    session.clear()
