"""Home Assistant API client for Simple Heating Manager."""

import logging
import os

import requests

_log = logging.getLogger(__name__)

SUPERVISOR_API = "http://supervisor/core/api"


class HomeAssistantAPI:
    """Client for the Home Assistant Supervisor API."""

    def __init__(self, notification_service: str = "persistent_notification.create"):
        token = os.environ.get("SUPERVISOR_TOKEN", "")
        if not token:
            raise RuntimeError("SUPERVISOR_TOKEN environment variable not set")
        self._headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        self._notification_service = notification_service

    def get_state(self, entity_id: str) -> dict:
        """Get the current state of an entity."""
        url = f"{SUPERVISOR_API}/states/{entity_id}"
        resp = requests.get(url, headers=self._headers, timeout=10)
        resp.raise_for_status()
        return resp.json()

    def call_service(self, domain: str, service: str, data: dict) -> None:
        """Call a Home Assistant service."""
        url = f"{SUPERVISOR_API}/services/{domain}/{service}"
        _log.debug("Calling service %s.%s with data: %s", domain, service, data)
        resp = requests.post(url, headers=self._headers, json=data, timeout=10)
        resp.raise_for_status()

    def set_trv_temperature(self, entity_id: str, temperature: float) -> None:
        """Set the target temperature on a climate entity."""
        _log.info("Setting %s temperature to %.1f", entity_id, temperature)
        self.call_service(
            "climate",
            "set_temperature",
            {"entity_id": entity_id, "temperature": temperature},
        )

    def set_trv_hvac_mode(self, entity_id: str, mode: str) -> None:
        """Set the HVAC mode on a climate entity."""
        _log.info("Setting %s HVAC mode to %s", entity_id, mode)
        self.call_service(
            "climate",
            "set_hvac_mode",
            {"entity_id": entity_id, "hvac_mode": mode},
        )

    def set_trv_offset(self, entity_id: str, offset: float) -> None:
        """Set the calibration offset on a number entity.

        Used for TRVs with a local_temperature_calibration entity
        (common with Zigbee TRVs).
        """
        _log.info("Setting %s offset to %.1f", entity_id, offset)
        self.call_service(
            "number",
            "set_value",
            {"entity_id": entity_id, "value": round(offset, 1)},
        )

    def send_notification(self, title: str, message: str) -> None:
        """Send a notification via the configured notification service."""
        domain, service = self._notification_service.rsplit(".", 1)
        _log.info("Sending notification: %s", title)
        self.call_service(domain, service, {"title": title, "message": message})

    def validate_entity(self, entity_id: str) -> bool:
        """Check if an entity exists in Home Assistant."""
        try:
            self.get_state(entity_id)
            return True
        except requests.exceptions.HTTPError as e:
            if e.response is not None and e.response.status_code == 404:
                return False
            raise
