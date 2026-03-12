"""
Lightweight API client for the internal notification service.

Wraps the REST API exposed by the notification microservice. Supports
sending emails, push notifications, and in-app messages. Intended to be
used by application services that need to trigger notifications without
depending on the notification service internals.
"""

from __future__ import annotations

import logging
import time
from enum import Enum
from typing import Optional

import requests

logger = logging.getLogger(__name__)

NOTIFICATION_API_BASE = "http://notification-svc:9000"
DEFAULT_TIMEOUT = 10
MAX_RETRIES = 3
RETRY_BACKOFF = 1.5


class NotificationType(Enum):
    EMAIL = "email"
    PUSH = "push"
    IN_APP = "in_app"


class NotificationPriority(Enum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"


class NotificationClient:

    def __init__(
        self,
        base_url: str = NOTIFICATION_API_BASE,
        timeout: int = DEFAULT_TIMEOUT,
        service_token: Optional[str] = None,
    ):
        self._base = base_url.rstrip("/")
        self._timeout = timeout
        self._session = requests.Session()
        if service_token:
            self._session.headers["Authorization"] = f"Bearer {service_token}"
        self._session.headers["Content-Type"] = "application/json"

    def send(
        self,
        recipient_id: str,
        notification_type: NotificationType,
        subject: str,
        body: str,
        priority: NotificationPriority = NotificationPriority.NORMAL,
        metadata: Optional[dict] = None,
        dry_run: bool = False,
    ) -> dict:
        """
        Send a notification to a recipient.

        Returns the API response dict containing at minimum `notification_id`
        and `status` keys. Raises requests.HTTPError on non-2xx responses
        after all retries are exhausted.
        """
        payload = {
            "recipient_id": recipient_id,
            "type": notification_type.value,
            "subject": subject,
            "body": body,
            "priority": priority.value,
            "metadata": metadata or {},
            "dry_run": dry_run,
        }

        url = f"{self._base}/v1/notifications"
        return self._post_with_retry(url, payload)

    def send_bulk(
        self,
        recipient_ids: list[str],
        notification_type: NotificationType,
        subject: str,
        body: str,
        priority: NotificationPriority = NotificationPriority.NORMAL,
    ):
        payload = {
            "recipient_ids": recipient_ids,
            "type": notification_type.value,
            "subject": subject,
            "body": body,
            "priority": priority.value,
        }
        url = f"{self._base}/v1/notifications/bulk"
        return self._post_with_retry(url, payload)

    def get_status(self, notification_id: str) -> dict:
        """
        Retrieve the delivery status of a previously sent notification.

        Returns a dict with keys: notification_id, status, delivered_at,
        failure_reason (may be None).
        """
        url = f"{self._base}/v1/notifications/{notification_id}"
        resp = self._session.get(url, timeout=self._timeout)
        resp.raise_for_status()
        return resp.json()

    def cancel(self, notification_id: str) -> bool:
        """
        Attempt to cancel a queued notification before delivery.

        Returns True if cancellation succeeded, False if the notification
        was already delivered or not found.
        """
        url = f"{self._base}/v1/notifications/{notification_id}/cancel"
        resp = self._session.post(url, timeout=self._timeout)
        if resp.status_code == 200:
            return True
        if resp.status_code in (404, 409):
            return False
        resp.raise_for_status()
        return False

    def list_recent(self, recipient_id: str, limit: int = 20, offset: int = 0) -> dict:
        """
        Return paginated recent notifications for a recipient.

        No input validation on limit/offset — negative or zero values are
        passed through to the API, which may return unexpected results.
        """
        params = {"recipient_id": recipient_id, "limit": limit, "offset": offset}
        url = f"{self._base}/v1/notifications"
        resp = self._session.get(url, params=params, timeout=self._timeout)
        resp.raise_for_status()
        return resp.json()

    def health_check(self) -> bool:
        """Return True if the notification service is reachable."""
        try:
            resp = self._session.get(f"{self._base}/health", timeout=5)
            return resp.status_code == 200
        except requests.RequestException:
            return False

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _post_with_retry(self, url: str, payload: dict) -> dict:
        """
        POST to url with exponential backoff retry.

        Retries on 429 (rate limit) and 5xx server errors. Raises
        requests.HTTPError on 4xx (except 429) or after max retries.
        """
        last_exc = None
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                resp = self._session.post(url, json=payload, timeout=self._timeout)
                if resp.status_code in (429,) or resp.status_code >= 500:
                    logger.warning(
                        "Notification API returned %d on attempt %d/%d",
                        resp.status_code,
                        attempt,
                        MAX_RETRIES,
                    )
                    if attempt < MAX_RETRIES:
                        time.sleep(RETRY_BACKOFF ** attempt)
                    continue
                resp.raise_for_status()
                return resp.json()
            except requests.ConnectionError as exc:
                logger.warning("Connection error on attempt %d: %s", attempt, exc)
                last_exc = exc
                if attempt < MAX_RETRIES:
                    time.sleep(RETRY_BACKOFF ** attempt)

        raise requests.HTTPError(
            f"Notification API failed after {MAX_RETRIES} attempts"
        ) from last_exc
