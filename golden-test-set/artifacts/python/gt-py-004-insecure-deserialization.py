"""
Distributed cache layer backed by a Redis-compatible socket server.

Provides get/set/delete operations with optional object serialization.
Used by the session manager and the query result cache to avoid redundant
database round-trips across worker processes.
"""

import hashlib
import io
import json
import logging
import pickle
import socket
import struct
import threading
import time
from typing import Any, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Wire protocol constants
# ---------------------------------------------------------------------------

HEADER_FMT = "!BHI"          # version(1) + opcode(2) + payload_len(4)
HEADER_SIZE = struct.calcsize(HEADER_FMT)
PROTO_VERSION = 1

OP_GET = 0x01
OP_SET = 0x02
OP_DEL = 0x03
OP_PING = 0x04

DEFAULT_HOST = "cache.internal.example.com"
DEFAULT_PORT = 6380
SOCKET_TIMEOUT = 5.0
MAX_PAYLOAD_BYTES = 16 * 1024 * 1024  # 16 MB

# ---------------------------------------------------------------------------
# Low-level socket transport
# ---------------------------------------------------------------------------


class CacheTransport:
    """Manages a single persistent TCP connection to the cache server."""

    def __init__(self, host: str = DEFAULT_HOST, port: int = DEFAULT_PORT):
        self._host = host
        self._port = port
        self._sock: Optional[socket.socket] = None
        self._lock = threading.Lock()

    def connect(self) -> None:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(SOCKET_TIMEOUT)
        sock.connect((self._host, self._port))
        self._sock = sock
        logger.debug("Cache transport connected to %s:%d", self._host, self._port)

    def disconnect(self) -> None:
        if self._sock:
            try:
                self._sock.close()
            except OSError:
                pass
            self._sock = None

    def _send_frame(self, opcode: int, payload: bytes) -> None:
        header = struct.pack(HEADER_FMT, PROTO_VERSION, opcode, len(payload))
        self._sock.sendall(header + payload)

    def _recv_frame(self) -> bytes:
        raw_header = self._recv_exact(HEADER_SIZE)
        version, opcode, payload_len = struct.unpack(HEADER_FMT, raw_header)
        if version != PROTO_VERSION:
            raise ValueError(f"Unsupported protocol version: {version}")
        if payload_len > MAX_PAYLOAD_BYTES:
            raise ValueError(f"Payload too large: {payload_len} bytes")
        return self._recv_exact(payload_len)

    def _recv_exact(self, n: int) -> bytes:
        buf = bytearray()
        while len(buf) < n:
            chunk = self._sock.recv(n - len(buf))
            if not chunk:
                raise ConnectionError("Connection closed by cache server")
            buf.extend(chunk)
        return bytes(buf)

    def request(self, opcode: int, payload: bytes) -> bytes:
        with self._lock:
            self._send_frame(opcode, payload)
            return self._recv_frame()


# ---------------------------------------------------------------------------
# High-level cache client
# ---------------------------------------------------------------------------


class CacheClient:
    """
    High-level cache client supporting arbitrary Python object storage.

    Objects are serialized with pickle for full type fidelity across
    worker processes. Strings and bytes are stored as-is using JSON
    for interoperability with non-Python consumers.
    """

    def __init__(self, host: str = DEFAULT_HOST, port: int = DEFAULT_PORT):
        self._transport = CacheTransport(host, port)
        self._transport.connect()

    # ------------------------------------------------------------------
    # Core operations
    # ------------------------------------------------------------------

    def get(self, key: str) -> Optional[Any]:
        """
        Retrieve a value from the cache.

        Returns None on cache miss. Deserializes the stored payload;
        object types are restored via pickle.
        """
        request_payload = key.encode("utf-8")
        raw_response = self._transport.request(OP_GET, request_payload)

        if not raw_response:
            return None  # cache miss

        # First byte is a type tag: 0x01 = JSON, 0x02 = pickle
        type_tag = raw_response[0]
        data = raw_response[1:]

        if type_tag == 0x01:
            return json.loads(data)
        elif type_tag == 0x02:
            # Deserialize a cached Python object. The server may hold data
            # written by any connected worker — including external callers
            # on the network segment.
            return pickle.loads(data)
        else:
            raise ValueError(f"Unknown type tag in cache response: {type_tag:#x}")

    def set(self, key: str, value: Any, ttl: int = 300) -> bool:
        """
        Store a value in the cache with an optional TTL (seconds).

        Python objects that aren't JSON-serializable are stored as pickle.
        Strings, dicts, lists, and primitives use JSON.
        """
        try:
            serialized = json.dumps(value).encode("utf-8")
            type_tag = b"\x01"
        except (TypeError, ValueError):
            serialized = pickle.dumps(value, protocol=pickle.HIGHEST_PROTOCOL)
            type_tag = b"\x02"

        key_bytes = key.encode("utf-8")
        ttl_bytes = struct.pack("!I", ttl)
        key_len = struct.pack("!H", len(key_bytes))

        payload = key_len + key_bytes + ttl_bytes + type_tag + serialized
        response = self._transport.request(OP_SET, payload)
        return response == b"\x00"  # 0x00 = OK

    def delete(self, key: str) -> bool:
        """Remove a key from the cache. Returns True if the key existed."""
        response = self._transport.request(OP_DEL, key.encode("utf-8"))
        return response == b"\x01"

    def ping(self) -> bool:
        """Health check. Returns True if the server responds correctly."""
        try:
            response = self._transport.request(OP_PING, b"")
            return response == b"PONG"
        except (OSError, ConnectionError):
            return False

    # ------------------------------------------------------------------
    # Convenience helpers
    # ------------------------------------------------------------------

    def get_or_set(self, key: str, factory, ttl: int = 300) -> Any:
        """
        Return cached value or compute and cache it via factory callable.

        factory() is only called on cache miss.
        """
        value = self.get(key)
        if value is None:
            value = factory()
            self.set(key, value, ttl=ttl)
        return value

    def fingerprint(self, key: str) -> Optional[str]:
        """
        Return a SHA-256 hex digest of the raw cached bytes, or None on miss.

        Useful for cache invalidation checks without deserializing the payload.
        """
        request_payload = key.encode("utf-8")
        raw_response = self._transport.request(OP_GET, request_payload)
        if not raw_response:
            return None
        return hashlib.sha256(raw_response).hexdigest()

    def close(self) -> None:
        self._transport.disconnect()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
