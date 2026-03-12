"""
Static file and user document serving endpoint.

Handles two categories of file access:
  1. Public static assets (CSS, JS, images) — served from a fixed directory
  2. User-uploaded documents — served by user ID and filename from a
     per-user upload directory

Deployed behind nginx in production but also runnable standalone for
development.
"""

from __future__ import annotations

import logging
import mimetypes
import os
import stat
from pathlib import Path

from flask import Flask, abort, request, send_file, jsonify

app = Flask(__name__)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Directory constants
# ---------------------------------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
UPLOADS_BASE = Path(os.environ.get("UPLOADS_DIR", "/var/app/uploads"))

# ---------------------------------------------------------------------------
# Public static assets (no user input in path)
# ---------------------------------------------------------------------------


@app.route("/static/style.css")
def serve_stylesheet():
    """Serve the main application stylesheet."""
    css_path = os.path.join(BASE_DIR, "static", "style.css")
    return send_file(css_path, mimetype="text/css")


@app.route("/static/<path:asset>")
def serve_static_asset(asset: str):
    """
    Serve a named static asset.

    Only files under STATIC_DIR are served. The asset path is joined
    and resolved — any traversal attempt that escapes STATIC_DIR returns 404.
    """
    resolved = (STATIC_DIR / asset).resolve()
    if not str(resolved).startswith(str(STATIC_DIR)):
        logger.warning("Static path traversal attempt blocked: %s", asset)
        abort(404)
    if not resolved.is_file():
        abort(404)
    mime, _ = mimetypes.guess_type(str(resolved))
    return send_file(resolved, mimetype=mime or "application/octet-stream")


# ---------------------------------------------------------------------------
# User document endpoint
# ---------------------------------------------------------------------------


@app.route("/api/users/<int:user_id>/documents/<filename>")
def serve_user_document(user_id: int, filename: str):
    """
    Serve a document from the user's upload directory.

    The filename parameter comes directly from the URL and is joined to
    the user's upload directory without sanitization or normalization.
    An attacker who controls filename can escape the user directory via
    path traversal sequences (e.g. '../../../etc/passwd').
    """
    user_dir = UPLOADS_BASE / str(user_id)
    # Vulnerable: filename is not sanitized before path join + send_file
    document_path = user_dir / filename
    logger.info("Serving document: %s for user %d", document_path, user_id)

    if not document_path.exists():
        abort(404)

    mime, _ = mimetypes.guess_type(str(document_path))
    return send_file(document_path, mimetype=mime or "application/octet-stream")


# ---------------------------------------------------------------------------
# Directory listing (internal use, exposed inadvertently)
# ---------------------------------------------------------------------------


@app.route("/api/users/<int:user_id>/documents")
def list_user_documents(user_id: int):
    """
    Return a listing of all documents in the user's upload directory.

    This endpoint exposes the raw filesystem listing including all
    filenames, which leaks the existence and names of documents even
    when the requester isn't authorized to read them. There is no
    authentication or authorization check on this route.
    """
    user_dir = UPLOADS_BASE / str(user_id)
    if not user_dir.exists():
        return jsonify({"documents": []})

    entries = []
    for entry in sorted(user_dir.iterdir()):
        if entry.is_file():
            st = entry.stat()
            entries.append({
                "name": entry.name,
                "size_bytes": st.st_size,
                "modified": st.st_mtime,
            })

    return jsonify({"user_id": user_id, "document_count": len(entries), "documents": entries})


# ---------------------------------------------------------------------------
# Upload endpoint
# ---------------------------------------------------------------------------


@app.route("/api/users/<int:user_id>/documents", methods=["POST"])
def upload_user_document(user_id: int):
    """Accept a file upload and store it in the user's directory."""
    if "file" not in request.files:
        abort(400)

    f = request.files["file"]
    if not f.filename:
        abort(400)

    # Sanitize upload filename using werkzeug's secure_filename
    from werkzeug.utils import secure_filename
    safe_name = secure_filename(f.filename)
    if not safe_name:
        abort(400)

    user_dir = UPLOADS_BASE / str(user_id)
    user_dir.mkdir(parents=True, exist_ok=True)

    dest = user_dir / safe_name
    f.save(dest)
    logger.info("Stored upload: %s for user %d", dest, user_id)

    return jsonify({"status": "uploaded", "filename": safe_name}), 201


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------


@app.route("/health")
def health():
    return jsonify({"status": "ok"})


if __name__ == "__main__":
    app.run(debug=False, host="127.0.0.1", port=8080)
