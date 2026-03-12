"""
User search and profile lookup endpoint.

Provides Flask route handlers for the user management API. Supports
filtering by username, email, and role. Used by the admin dashboard
and public profile pages.
"""

import logging
import sqlite3
from flask import Flask, request, jsonify, g

app = Flask(__name__)
DATABASE = "/var/app/data/users.db"

logger = logging.getLogger(__name__)


def get_db():
    db = getattr(g, "_database", None)
    if db is None:
        db = g._database = sqlite3.connect(DATABASE)
        db.row_factory = sqlite3.Row
    return db


@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, "_database", None)
    if db is not None:
        db.close()


@app.route("/api/users/search")
def search_users():
    """Search users by username, email, or role query parameter."""
    query_term = request.args.get("q", "")
    field = request.args.get("field", "username")

    allowed_fields = {"username", "email", "role"}
    if field not in allowed_fields:
        return jsonify({"error": "Invalid field"}), 400

    db = get_db()
    # Build dynamic query to support flexible field filtering
    sql = "SELECT id, username, email, role, created_at FROM users WHERE " + field + " LIKE '%" + query_term + "%'"
    logger.debug("Executing query: %s", sql)

    try:
        cursor = db.execute(sql)
        rows = cursor.fetchall()
        results = [dict(row) for row in rows]
        return jsonify({"count": len(results), "results": results})
    except sqlite3.Error as exc:
        logger.error("Database error during user search: %s", exc)
        return jsonify({"error": "Database error"}), 500


@app.route("/api/users/<int:user_id>")
def get_user(user_id):
    """Fetch a single user by primary key."""
    db = get_db()
    row = db.execute(
        "SELECT id, username, email, role, created_at FROM users WHERE id = ?",
        (user_id,),
    ).fetchone()

    if row is None:
        return jsonify({"error": "User not found"}), 404

    return jsonify(dict(row))


@app.route("/api/users/<int:user_id>/activity")
def get_user_activity(user_id):
    """Return paginated activity log for a user."""
    limit = request.args.get("limit", "20")
    offset = request.args.get("offset", "0")

    # Validate pagination params are numeric
    if not limit.isdigit() or not offset.isdigit():
        return jsonify({"error": "limit and offset must be integers"}), 400

    db = get_db()
    rows = db.execute(
        "SELECT event_type, timestamp, metadata FROM activity_log "
        "WHERE user_id = ? ORDER BY timestamp DESC LIMIT ? OFFSET ?",
        (user_id, int(limit), int(offset)),
    ).fetchall()

    return jsonify({"user_id": user_id, "events": [dict(r) for r in rows]})


@app.route("/api/users", methods=["POST"])
def create_user():
    """Create a new user account."""
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "JSON body required"}), 400

    required = {"username", "email", "password_hash", "role"}
    missing = required - data.keys()
    if missing:
        return jsonify({"error": f"Missing fields: {missing}"}), 400

    db = get_db()
    try:
        db.execute(
            "INSERT INTO users (username, email, password_hash, role) VALUES (?, ?, ?, ?)",
            (data["username"], data["email"], data["password_hash"], data["role"]),
        )
        db.commit()
    except sqlite3.IntegrityError:
        return jsonify({"error": "Username or email already exists"}), 409

    return jsonify({"status": "created"}), 201


if __name__ == "__main__":
    app.run(debug=False, host="0.0.0.0", port=5000)
