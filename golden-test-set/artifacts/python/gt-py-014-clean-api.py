"""
REST API client for the inventory management service.

Provides typed access to inventory records, stock level queries, and
reservation operations. Implements exponential backoff with jitter,
connection pooling, request correlation IDs, and structured error handling.

Intended for use by fulfillment services, the warehouse management system,
and the demand forecasting pipeline.
"""

from __future__ import annotations

import logging
import random
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Iterator, Optional

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DEFAULT_BASE_URL = "http://inventory-svc:8080"
DEFAULT_TIMEOUT = (5.0, 30.0)   # (connect timeout, read timeout) in seconds
MAX_RETRIES = 3
RETRY_BACKOFF_BASE = 0.5        # seconds
RETRY_BACKOFF_MAX = 10.0        # seconds
RETRY_STATUS_FORCELIST = (429, 500, 502, 503, 504)
PAGE_SIZE = 100

# ---------------------------------------------------------------------------
# Domain types
# ---------------------------------------------------------------------------


class StockStatus(Enum):
    IN_STOCK = "in_stock"
    LOW_STOCK = "low_stock"
    OUT_OF_STOCK = "out_of_stock"
    DISCONTINUED = "discontinued"


@dataclass
class InventoryItem:
    sku: str
    name: str
    quantity_on_hand: int
    quantity_reserved: int
    warehouse_id: str
    status: StockStatus
    unit_cost_cents: int
    reorder_threshold: int
    last_updated: str           # ISO 8601

    @property
    def quantity_available(self) -> int:
        return max(0, self.quantity_on_hand - self.quantity_reserved)

    @classmethod
    def from_dict(cls, data: dict) -> "InventoryItem":
        return cls(
            sku=data["sku"],
            name=data["name"],
            quantity_on_hand=int(data["quantity_on_hand"]),
            quantity_reserved=int(data.get("quantity_reserved", 0)),
            warehouse_id=data["warehouse_id"],
            status=StockStatus(data["status"]),
            unit_cost_cents=int(data["unit_cost_cents"]),
            reorder_threshold=int(data.get("reorder_threshold", 0)),
            last_updated=data["last_updated"],
        )


@dataclass
class ReservationResult:
    reservation_id: str
    sku: str
    quantity: int
    warehouse_id: str
    expires_at: str
    status: str


@dataclass
class ClientConfig:
    base_url: str = DEFAULT_BASE_URL
    timeout: tuple = field(default_factory=lambda: DEFAULT_TIMEOUT)
    service_token: Optional[str] = None
    max_retries: int = MAX_RETRIES

# ---------------------------------------------------------------------------
# Error types
# ---------------------------------------------------------------------------


class InventoryError(Exception):
    """Base class for inventory client errors."""


class InsufficientStockError(InventoryError):
    """Raised when a reservation cannot be fulfilled due to stock."""

    def __init__(self, sku: str, requested: int, available: int):
        self.sku = sku
        self.requested = requested
        self.available = available
        super().__init__(
            f"Insufficient stock for {sku}: requested {requested}, available {available}"
        )


class ItemNotFoundError(InventoryError):
    """Raised when the requested SKU does not exist in the system."""


# ---------------------------------------------------------------------------
# Session factory
# ---------------------------------------------------------------------------


def _build_session(config: ClientConfig) -> requests.Session:
    """
    Build a requests.Session with connection pooling and retry logic.

    Retries are handled at the urllib3 layer for idempotent requests
    (GET, HEAD, OPTIONS). POST retries are handled at the application layer
    in _request() to avoid double-booking on reservation endpoints.
    """
    session = requests.Session()

    retry = Retry(
        total=config.max_retries,
        backoff_factor=RETRY_BACKOFF_BASE,
        status_forcelist=RETRY_STATUS_FORCELIST,
        allowed_methods=["GET", "HEAD", "OPTIONS"],
        raise_on_status=False,
    )
    adapter = HTTPAdapter(
        max_retries=retry,
        pool_connections=4,
        pool_maxsize=16,
    )
    session.mount("http://", adapter)
    session.mount("https://", adapter)

    if config.service_token:
        session.headers["Authorization"] = f"Bearer {config.service_token}"

    session.headers.update({
        "Accept": "application/json",
        "Content-Type": "application/json",
    })

    return session


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------


class InventoryClient:
    """
    Thread-safe client for the inventory management API.

    All public methods raise InventoryError subclasses on domain errors
    and requests.RequestException on network/HTTP transport errors.
    """

    def __init__(self, config: Optional[ClientConfig] = None):
        self._cfg = config or ClientConfig()
        self._session = _build_session(self._cfg)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_item(self, sku: str) -> InventoryItem:
        """
        Fetch a single inventory item by SKU.

        Raises ItemNotFoundError if the SKU does not exist.
        Raises InventoryError on other API errors.
        """
        data = self._request("GET", f"/v1/inventory/{sku}")
        return InventoryItem.from_dict(data)

    def list_items(
        self,
        warehouse_id: Optional[str] = None,
        status: Optional[StockStatus] = None,
        low_stock_only: bool = False,
    ) -> list[InventoryItem]:
        """
        Return all inventory items matching the given filters.

        Handles pagination internally. Returns a flat list.
        """
        params: dict = {"page_size": PAGE_SIZE}
        if warehouse_id:
            params["warehouse_id"] = warehouse_id
        if status:
            params["status"] = status.value
        if low_stock_only:
            params["low_stock_only"] = "true"

        items = []
        for page in self._paginate("/v1/inventory", params):
            items.extend(InventoryItem.from_dict(rec) for rec in page)
        return items

    def reserve(
        self,
        sku: str,
        quantity: int,
        warehouse_id: str,
        order_id: str,
        ttl_seconds: int = 900,
    ) -> ReservationResult:
        """
        Reserve inventory for an order.

        Parameters
        ----------
        sku:
            Stock-keeping unit identifier.
        quantity:
            Number of units to reserve.
        warehouse_id:
            The warehouse to reserve from.
        order_id:
            Caller's order reference (used for idempotency key).
        ttl_seconds:
            How long to hold the reservation (default 15 minutes).

        Returns
        -------
        ReservationResult

        Raises
        ------
        InsufficientStockError:
            If the warehouse cannot fulfill the quantity.
        InventoryError:
            On other domain errors.
        """
        if quantity <= 0:
            raise ValueError(f"quantity must be positive, got {quantity}")
        if ttl_seconds <= 0 or ttl_seconds > 86400:
            raise ValueError("ttl_seconds must be between 1 and 86400")

        payload = {
            "sku": sku,
            "quantity": quantity,
            "warehouse_id": warehouse_id,
            "order_id": order_id,
            "ttl_seconds": ttl_seconds,
        }
        data = self._request("POST", "/v1/reservations", json=payload)
        return ReservationResult(
            reservation_id=data["reservation_id"],
            sku=data["sku"],
            quantity=data["quantity"],
            warehouse_id=data["warehouse_id"],
            expires_at=data["expires_at"],
            status=data["status"],
        )

    def cancel_reservation(self, reservation_id: str) -> bool:
        """
        Cancel a pending reservation.

        Returns True if cancelled, False if already expired or fulfilled.
        """
        try:
            self._request("DELETE", f"/v1/reservations/{reservation_id}")
            return True
        except InventoryError as exc:
            if "not_found" in str(exc).lower() or "expired" in str(exc).lower():
                return False
            raise

    def adjust_stock(self, sku: str, warehouse_id: str, delta: int, reason: str) -> InventoryItem:
        """
        Adjust on-hand stock by a signed delta (positive = receipt, negative = shrinkage).

        Returns the updated InventoryItem.
        """
        payload = {
            "delta": delta,
            "warehouse_id": warehouse_id,
            "reason": reason,
        }
        data = self._request("POST", f"/v1/inventory/{sku}/adjust", json=payload)
        return InventoryItem.from_dict(data)

    def health(self) -> bool:
        """Return True if the inventory service is healthy."""
        url = f"{self._cfg.base_url}/health"
        try:
            resp = self._session.get(url, timeout=self._cfg.timeout)
            return resp.status_code == 200
        except requests.RequestException:
            return False

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _request(
        self,
        method: str,
        path: str,
        json: Optional[dict] = None,
        params: Optional[dict] = None,
        _attempt: int = 1,
    ) -> dict:
        """
        Execute an HTTP request against the inventory API.

        Handles error response mapping to domain exceptions. Retries POST
        requests with exponential backoff + jitter on 429/5xx.
        """
        url = f"{self._cfg.base_url}{path}"
        correlation_id = str(uuid.uuid4())
        headers = {"X-Correlation-ID": correlation_id}

        try:
            resp = self._session.request(
                method,
                url,
                json=json,
                params=params,
                headers=headers,
                timeout=self._cfg.timeout,
            )
        except requests.ConnectionError as exc:
            raise InventoryError(f"Cannot connect to inventory service: {exc}") from exc
        except requests.Timeout as exc:
            raise InventoryError(f"Request timed out: {exc}") from exc

        # Handle retry-able responses for non-GET methods (GET is handled by urllib3)
        if method not in ("GET", "HEAD") and resp.status_code in RETRY_STATUS_FORCELIST:
            if _attempt <= self._cfg.max_retries:
                wait = min(
                    RETRY_BACKOFF_BASE * (2 ** (_attempt - 1)) + random.uniform(0, 0.5),
                    RETRY_BACKOFF_MAX,
                )
                logger.warning(
                    "Request %s %s returned %d (correlation=%s); retry %d/%d in %.1fs",
                    method, path, resp.status_code, correlation_id,
                    _attempt, self._cfg.max_retries, wait,
                )
                time.sleep(wait)
                return self._request(method, path, json=json, params=params, _attempt=_attempt + 1)

        if resp.status_code == 404:
            raise ItemNotFoundError(f"Resource not found: {path}")
        if resp.status_code == 409:
            body = self._safe_json(resp)
            available = body.get("available", 0)
            requested = json.get("quantity", 0) if json else 0
            sku = (json or {}).get("sku", path)
            raise InsufficientStockError(sku, requested, available)
        if not resp.ok:
            body = self._safe_json(resp)
            message = body.get("message", resp.text[:200])
            raise InventoryError(
                f"API error {resp.status_code} [{correlation_id}]: {message}"
            )

        return self._safe_json(resp)

    def _paginate(self, path: str, params: dict) -> Iterator[list]:
        """Yield successive pages of results from a paginated list endpoint."""
        page_params = {**params, "page": 1}
        while True:
            resp = self._request("GET", path, params=page_params)
            items = resp.get("items", [])
            if not items:
                break
            yield items
            if not resp.get("has_next"):
                break
            page_params["page"] += 1

    @staticmethod
    def _safe_json(resp: requests.Response) -> dict:
        """Parse response JSON, returning empty dict on parse failure."""
        try:
            return resp.json()
        except ValueError:
            return {}

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self._session.close()
