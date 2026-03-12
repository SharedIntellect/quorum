"""
user_mgmt_svc/api/routes.py — User Management API route handlers

Implements the endpoints defined in spec.md v2.1.
Service: user-mgmt-svc
Author: backend-platform-eng
Last updated: 2026-02-14
"""

from __future__ import annotations

import base64
import logging
import uuid
from functools import wraps
from typing import Any

from flask import Flask, jsonify, request, g
from werkzeug.exceptions import HTTPException

from .db import db_session, User
from .rate_limiter import rate_limit
from .audit import audit_log

logger = logging.getLogger(__name__)
app = Flask(__name__)


# ── Authentication helpers ────────────────────────────────────────────────────

def _decode_jwt(token: str) -> dict[str, Any] | None:
    """Decode and verify a JWT Bearer token. Returns claims dict or None."""
    from .jwt_utils import verify_and_decode
    try:
        return verify_and_decode(token)
    except Exception:
        return None


def require_jwt(f):
    """Decorator: require a valid JWT Bearer token."""
    @wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return jsonify({"error": {"code": "UNAUTHORIZED", "message": "Bearer token required",
                                      "request_id": g.get("request_id", "")}}), 401
        token = auth_header[len("Bearer "):]
        claims = _decode_jwt(token)
        if claims is None:
            return jsonify({"error": {"code": "UNAUTHORIZED", "message": "Invalid token",
                                      "request_id": g.get("request_id", "")}}), 401
        g.jwt_claims = claims
        return f(*args, **kwargs)
    return decorated


def require_basic_auth(f):
    """Decorator: require HTTP Basic authentication for admin endpoints."""
    @wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Basic "):
            return jsonify({"error": {"code": "UNAUTHORIZED", "message": "Basic auth required",
                                      "request_id": g.get("request_id", "")}}), 401
        try:
            decoded = base64.b64decode(auth_header[6:]).decode("utf-8")
            username, password = decoded.split(":", 1)
        except Exception:
            return jsonify({"error": {"code": "UNAUTHORIZED", "message": "Malformed Basic auth",
                                      "request_id": g.get("request_id", "")}}), 401
        from .admin_users import verify_admin_password
        if not verify_admin_password(username, password):
            return jsonify({"error": {"code": "FORBIDDEN", "message": "Invalid admin credentials",
                                      "request_id": g.get("request_id", "")}}), 403
        g.admin_user = username
        return f(*args, **kwargs)
    return decorated


# ── Route: GET /api/users ─────────────────────────────────────────────────────

@app.route("/api/users", methods=["GET"])
@rate_limit(100, window=60)
@require_jwt
def list_users():
    page  = max(1, request.args.get("page",  1,   type=int))
    limit = min(100, max(1, request.args.get("limit", 20, type=int)))
    filt  = request.args.get("filter", "")

    with db_session() as session:
        q = session.query(User)
        if filt:
            q = q.filter(User.username.ilike(f"%{filt}%"))
        total = q.count()
        users = q.offset((page - 1) * limit).limit(limit).all()

    return jsonify({
        "users": [u.to_dict() for u in users],
        "total": total,
        "page":  page,
        "limit": limit,
    }), 200


# ── Route: GET /api/users/<id> ────────────────────────────────────────────────

@app.route("/api/users/<user_id>", methods=["GET"])
@rate_limit(200, window=60)
@require_jwt
def get_user(user_id: str):
    try:
        uid = uuid.UUID(user_id)
    except ValueError:
        return jsonify({"error": {"code": "BAD_REQUEST", "message": "Invalid UUID",
                                  "request_id": g.get("request_id", "")}}), 400

    with db_session() as session:
        user = session.query(User).filter_by(id=uid).first()
        if user is None:
            return jsonify({"error": {"code": "NOT_FOUND", "message": "User not found",
                                      "request_id": g.get("request_id", "")}}), 404
        return jsonify(user.to_dict()), 200


# ── Route: POST /api/users ────────────────────────────────────────────────────

@app.route("/api/users", methods=["POST"])
@rate_limit(10, window=60)
@require_jwt
def create_user():
    data = request.get_json(force=True, silent=True) or {}
    username = data.get("username", "").strip()
    email    = data.get("email",    "").strip()
    role     = data.get("role",     "").strip()

    if not username or not email or not role:
        return jsonify({"error": {"code": "BAD_REQUEST",
                                  "message": "username, email, and role are required",
                                  "request_id": g.get("request_id", "")}}), 400

    if role not in ("viewer", "editor", "admin"):
        return jsonify({"error": {"code": "BAD_REQUEST",
                                  "message": "role must be viewer, editor, or admin",
                                  "request_id": g.get("request_id", "")}}), 400

    with db_session() as session:
        if session.query(User).filter(
            (User.username == username) | (User.email == email)
        ).first():
            return jsonify({"error": {"code": "CONFLICT",
                                      "message": "Username or email already exists",
                                      "request_id": g.get("request_id", "")}}), 409

        new_user = User(id=uuid.uuid4(), username=username, email=email, role=role)
        session.add(new_user)
        session.commit()
        return jsonify(new_user.to_dict()), 201


# ── Route: PUT /api/users/<id> ────────────────────────────────────────────────

@app.route("/api/users/<user_id>", methods=["PUT"])
@rate_limit(20, window=60)
@require_jwt
def update_user(user_id: str):
    try:
        uid = uuid.UUID(user_id)
    except ValueError:
        return jsonify({"error": {"code": "BAD_REQUEST", "message": "Invalid UUID",
                                  "request_id": g.get("request_id", "")}}), 400

    data = request.get_json(force=True, silent=True) or {}

    with db_session() as session:
        user = session.query(User).filter_by(id=uid).first()
        if user is None:
            return jsonify({"error": {"code": "NOT_FOUND", "message": "User not found",
                                      "request_id": g.get("request_id", "")}}), 404

        if "username" in data:
            user.username = data["username"].strip()
        if "email" in data:
            user.email = data["email"].strip()
        if "role" in data:
            if data["role"] not in ("viewer", "editor", "admin"):
                return jsonify({"error": {"code": "BAD_REQUEST", "message": "Invalid role",
                                          "request_id": g.get("request_id", "")}}), 400
            user.role = data["role"]

        session.commit()
        return jsonify(user.to_dict()), 200


# ── Route: GET /api/admin/stats ───────────────────────────────────────────────

@app.route("/api/admin/stats", methods=["GET"])
@rate_limit(10, window=60)
@require_basic_auth
def admin_stats():
    from .analytics import get_user_stats
    stats = get_user_stats()
    return jsonify(stats), 200


# ── Error handlers ────────────────────────────────────────────────────────────

@app.errorhandler(HTTPException)
def handle_http_exception(e: HTTPException):
    return jsonify({"error": {"code": e.name.upper().replace(" ", "_"),
                              "message": e.description,
                              "request_id": g.get("request_id", "")}}), e.code


@app.errorhandler(Exception)
def handle_unexpected(e: Exception):
    logger.exception("Unhandled exception: %s", e)
    return jsonify({"error": {"code": "INTERNAL_SERVER_ERROR",
                              "message": "An unexpected error occurred.",
                              "request_id": g.get("request_id", "")}}), 500
