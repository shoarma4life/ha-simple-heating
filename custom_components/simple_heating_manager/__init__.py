"""Simple Heating Manager - HACS custom integration.

Manages heating per room with TRV calibration and window detection.
Each config entry represents one room.
"""

from __future__ import annotations

from datetime import timedelta
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.event import async_track_time_interval

from .const import (
    CONF_CALIBRATION_MODE,
    CONF_CHECK_INTERVAL,
    CONF_CV_SWITCH,
    CONF_NAME,
    CONF_NOTIFICATION_SERVICE,
    CONF_TARGET_TEMP,
    CONF_TEMP_SENSOR,
    CONF_TRV_ENTITY,
    CONF_WINDOW_SENSORS,
    DEFAULT_CALIBRATION_MODE,
    DEFAULT_CHECK_INTERVAL,
    DEFAULT_NOTIFICATION_SERVICE,
    DEFAULT_TARGET_TEMP,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)


class Room:
    """Manages heating logic for a single room."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize room from config entry."""
        self.hass = hass
        self.entry = entry

        self.name: str = entry.data[CONF_NAME]
        self.trv_entity: str = entry.data[CONF_TRV_ENTITY]
        self.temp_sensor: str = entry.data[CONF_TEMP_SENSOR]
        self.window_sensors: list[str] = entry.data.get(CONF_WINDOW_SENSORS, []) or []
        self.calibration_mode: str = entry.data.get(
            CONF_CALIBRATION_MODE, DEFAULT_CALIBRATION_MODE
        )
        self.target_temperature: float = entry.data.get(
            CONF_TARGET_TEMP, DEFAULT_TARGET_TEMP
        )
        self.notification_service: str = entry.data.get(
            CONF_NOTIFICATION_SERVICE, DEFAULT_NOTIFICATION_SERVICE
        )
        self.cv_switch: str | None = entry.data.get(CONF_CV_SWITCH)

        self.window_open: bool = False
        self.needs_heat: bool = False
        self.previous_hvac_mode: str | None = None
        self.previous_temperature: float | None = None
        self.last_calibration_offset: float = 0.0

    def update(self) -> None:
        """Main update cycle for this room."""
        try:
            windows_open = self._check_windows()

            if windows_open and not self.window_open:
                self._handle_window_opened()
            elif not windows_open and self.window_open:
                self._handle_window_closed()

            if not windows_open:
                self._calibrate()

        except Exception:
            _LOGGER.exception("Error updating room '%s'", self.name)

    def _check_windows(self) -> bool:
        """Check if any window sensor reports open."""
        for sensor_id in self.window_sensors:
            try:
                state = self.hass.states.get(sensor_id)
                if state is not None and state.state == "on":
                    _LOGGER.debug(
                        "Room '%s': window sensor %s is open",
                        self.name,
                        sensor_id,
                    )
                    return True
            except Exception:
                _LOGGER.exception(
                    "Room '%s': error reading window sensor %s",
                    self.name,
                    sensor_id,
                )
        return False

    def _handle_window_opened(self) -> None:
        """Handle window opening: save state and turn off TRV."""
        _LOGGER.info(
            "Room '%s': window opened, turning off heating", self.name
        )

        try:
            trv_state = self.hass.states.get(self.trv_entity)
            if trv_state is not None:
                self.previous_hvac_mode = trv_state.state
                self.previous_temperature = trv_state.attributes.get("temperature")
            else:
                self.previous_hvac_mode = "heat"
                self.previous_temperature = None
        except Exception:
            _LOGGER.exception(
                "Room '%s': error reading TRV state before turning off",
                self.name,
            )
            self.previous_hvac_mode = "heat"
            self.previous_temperature = None

        try:
            self.hass.services.call(
                "climate",
                "set_hvac_mode",
                {"entity_id": self.trv_entity, "hvac_mode": "off"},
            )
        except Exception:
            _LOGGER.exception(
                "Room '%s': error turning off TRV", self.name
            )

        self.window_open = True
        self._send_notification(
            f"Room '{self.name}': window opened, heating turned off."
        )

    def _handle_window_closed(self) -> None:
        """Handle window closing: restore previous TRV state."""
        _LOGGER.info(
            "Room '%s': window closed, restoring heating", self.name
        )

        try:
            mode = self.previous_hvac_mode
            if not mode or mode == "off":
                mode = "heat"
            self.hass.services.call(
                "climate",
                "set_hvac_mode",
                {"entity_id": self.trv_entity, "hvac_mode": mode},
            )

            if self.previous_temperature is not None:
                self.hass.services.call(
                    "climate",
                    "set_temperature",
                    {
                        "entity_id": self.trv_entity,
                        "temperature": self.previous_temperature,
                    },
                )
        except Exception:
            _LOGGER.exception(
                "Room '%s': error restoring TRV state", self.name
            )

        self.window_open = False
        self.previous_hvac_mode = None
        self.previous_temperature = None

        self._send_notification(
            f"Room '{self.name}': window closed, heating restored."
        )

    def _calibrate(self) -> None:
        """Perform TRV calibration based on external temperature sensor."""
        if self.calibration_mode == "none":
            return

        # Read external temperature
        try:
            ext_state = self.hass.states.get(self.temp_sensor)
            if ext_state is None or ext_state.state in ("unknown", "unavailable"):
                _LOGGER.warning(
                    "Room '%s': external sensor %s unavailable",
                    self.name,
                    self.temp_sensor,
                )
                return
            external_temp = float(ext_state.state)
        except (ValueError, TypeError):
            _LOGGER.warning(
                "Room '%s': could not read external temperature from %s",
                self.name,
                self.temp_sensor,
            )
            return

        # Read TRV internal temperature
        try:
            trv_state = self.hass.states.get(self.trv_entity)
            if trv_state is None:
                _LOGGER.warning(
                    "Room '%s': TRV %s not found", self.name, self.trv_entity
                )
                return
            trv_internal_temp = trv_state.attributes.get("current_temperature")
            if trv_internal_temp is None:
                _LOGGER.warning(
                    "Room '%s': TRV %s has no current_temperature attribute",
                    self.name,
                    self.trv_entity,
                )
                return
            trv_internal_temp = float(trv_internal_temp)
        except (ValueError, TypeError):
            _LOGGER.warning(
                "Room '%s': could not parse TRV internal temperature",
                self.name,
            )
            return

        if self.calibration_mode == "offset":
            self._calibrate_offset(external_temp, trv_internal_temp)
        elif self.calibration_mode == "target_temp":
            self._calibrate_target_temp(external_temp, trv_internal_temp)

    def _calibrate_offset(
        self, external_temp: float, trv_internal_temp: float
    ) -> None:
        """Calibrate using offset mode.

        Calculates the difference between external and TRV internal temperature
        and sets it as the calibration offset on the TRV's offset entity.
        """
        offset = round(external_temp - trv_internal_temp, 1)

        if offset == self.last_calibration_offset:
            _LOGGER.debug(
                "Room '%s': offset unchanged (%.1f), skipping",
                self.name,
                offset,
            )
            return

        # Derive the offset entity from the TRV entity name
        # e.g., climate.living_room_trv -> number.living_room_trv_local_temperature_calibration
        trv_name = self.trv_entity.split(".", 1)[1]
        offset_entity = f"number.{trv_name}_local_temperature_calibration"

        _LOGGER.info(
            "Room '%s': setting offset to %.1f (external=%.1f, trv=%.1f)",
            self.name,
            offset,
            external_temp,
            trv_internal_temp,
        )

        try:
            self.hass.services.call(
                "number",
                "set_value",
                {"entity_id": offset_entity, "value": round(offset, 1)},
            )
            self.last_calibration_offset = offset
        except Exception:
            _LOGGER.exception(
                "Room '%s': error setting calibration offset on %s",
                self.name,
                offset_entity,
            )

    def _calibrate_target_temp(
        self, external_temp: float, trv_internal_temp: float
    ) -> None:
        """Calibrate using target temperature mode.

        Adjusts the TRV target temperature to compensate for the difference
        between external and TRV internal temperature readings.

        Example: desired 21C, external reads 19C, TRV reads 21C
        -> delta = 19 - 21 = -2
        -> adjusted_target = 21 - (-2) = 23C (TRV heats more)
        """
        if self.target_temperature is None:
            return

        delta = external_temp - trv_internal_temp
        adjusted_target = round(self.target_temperature - delta, 1)

        _LOGGER.info(
            "Room '%s': target_temp calibration: desired=%.1f, "
            "external=%.1f, trv_internal=%.1f, delta=%.1f, adjusted=%.1f",
            self.name,
            self.target_temperature,
            external_temp,
            trv_internal_temp,
            delta,
            adjusted_target,
        )

        try:
            self.hass.services.call(
                "climate",
                "set_temperature",
                {"entity_id": self.trv_entity, "temperature": adjusted_target},
            )
        except Exception:
            _LOGGER.exception(
                "Room '%s': error setting adjusted target temperature",
                self.name,
            )

    def _send_notification(self, message: str) -> None:
        """Send a notification via the configured notification service."""
        try:
            parts = self.notification_service.rsplit(".", 1)
            if len(parts) != 2:
                _LOGGER.warning(
                    "Room '%s': invalid notification service '%s'",
                    self.name,
                    self.notification_service,
                )
                return
            domain, service = parts
            self.hass.services.call(
                domain,
                service,
                {"title": "Heating Manager", "message": message},
            )
        except Exception:
            _LOGGER.exception(
                "Room '%s': error sending notification", self.name
            )

    def check_heat_demand(self) -> None:
        """Determine if this room's TRV is actively requesting heat."""
        if self.window_open:
            self.needs_heat = False
            return

        try:
            trv_state = self.hass.states.get(self.trv_entity)
            if trv_state is None:
                self.needs_heat = False
                return

            # Primary: use hvac_action attribute (most reliable)
            hvac_action = trv_state.attributes.get("hvac_action")
            if hvac_action is not None:
                self.needs_heat = hvac_action == "heating"
                return

            # Fallback: compare current_temperature to target
            if trv_state.state == "off":
                self.needs_heat = False
                return
            current = trv_state.attributes.get("current_temperature")
            target = trv_state.attributes.get("temperature")
            if current is not None and target is not None:
                self.needs_heat = float(current) < float(target)
            else:
                self.needs_heat = False
        except Exception:
            _LOGGER.exception(
                "Room '%s': error checking heat demand", self.name
            )
            self.needs_heat = False


def _update_cv_switches(hass: HomeAssistant) -> None:
    """Update all CV boiler switches across rooms.

    A switch is turned ON if any room using it needs heat.
    A switch is turned OFF only when no room using it needs heat.
    """
    rooms_data = hass.data.get(DOMAIN, {})

    # Group rooms by their cv_switch entity
    switch_demand: dict[str, bool] = {}
    for entry_data in rooms_data.values():
        room: Room = entry_data["room"]
        if not room.cv_switch:
            continue
        # If any room needs heat, the switch should be on
        if room.cv_switch not in switch_demand:
            switch_demand[room.cv_switch] = False
        if room.needs_heat:
            switch_demand[room.cv_switch] = True

    for switch_entity, any_needs_heat in switch_demand.items():
        try:
            current_state = hass.states.get(switch_entity)
            if current_state is None:
                _LOGGER.warning("CV switch %s not found", switch_entity)
                continue

            is_on = current_state.state == "on"
            domain = switch_entity.split(".", 1)[0]

            if any_needs_heat and not is_on:
                _LOGGER.info("CV switch %s: turning ON (heat demanded)", switch_entity)
                hass.services.call(
                    domain, "turn_on", {"entity_id": switch_entity}
                )
            elif not any_needs_heat and is_on:
                _LOGGER.info(
                    "CV switch %s: turning OFF (no room needs heat)", switch_entity
                )
                hass.services.call(
                    domain, "turn_off", {"entity_id": switch_entity}
                )
        except Exception:
            _LOGGER.exception("Error updating CV switch %s", switch_entity)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Simple Heating Manager from a config entry (one room)."""
    room = Room(hass, entry)
    interval = entry.data.get(CONF_CHECK_INTERVAL, DEFAULT_CHECK_INTERVAL)

    _LOGGER.info(
        "Setting up room '%s' (TRV: %s, sensor: %s, interval: %ds)",
        room.name,
        room.trv_entity,
        room.temp_sensor,
        interval,
    )

    def _update(_now=None) -> None:
        """Periodic update callback."""
        room.update()
        room.check_heat_demand()
        _update_cv_switches(hass)

    cancel = async_track_time_interval(
        hass, _update, timedelta(seconds=interval)
    )

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {
        "room": room,
        "cancel": cancel,
    }

    entry.async_on_unload(
        entry.add_update_listener(_async_update_listener)
    )

    return True


async def _async_update_listener(
    hass: HomeAssistant, entry: ConfigEntry
) -> None:
    """Handle options update — reload the entry."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    data = hass.data[DOMAIN].pop(entry.entry_id, None)
    if data and data.get("cancel"):
        data["cancel"]()
    _LOGGER.info("Unloaded room '%s'", entry.data.get(CONF_NAME, "unknown"))
    return True
