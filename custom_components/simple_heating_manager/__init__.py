"""Simple Heating Manager - HACS custom integration.

Architecture: separate config entries for global settings and each room.
- Global entry: CV switches, notification service
- Room entries: TRV, temp sensor, window sensors, etc.
"""

from __future__ import annotations

from datetime import timedelta
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import Event, HomeAssistant
from homeassistant.helpers.event import (
    async_track_state_change_event,
    async_track_time_interval,
)

from .const import (
    CONF_CHECK_INTERVAL,
    CONF_CV_SWITCH_1,
    CONF_CV_SWITCH_2,
    CONF_ENTRY_TYPE,
    CONF_NOTIFICATION_SERVICE,
    CONF_ROOM_NAME,
    CONF_ROOM_SWITCH,
    CONF_SENSOR_MODE_ENTITY,
    CONF_TEMP_SENSOR,
    CONF_TRV_ENTITY,
    CONF_WINDOW_SENSORS,
    DEFAULT_CHECK_INTERVAL,
    DEFAULT_NOTIFICATION_SERVICE,
    DOMAIN,
    ENTRY_TYPE_GLOBAL,
    ENTRY_TYPE_ROOM,
)

_LOGGER = logging.getLogger(__name__)

PLATFORMS = ["sensor", "button"]


class Room:
    """Manages heating logic for a single room."""

    def __init__(self, hass: HomeAssistant, room_cfg: dict) -> None:
        self.hass = hass
        self.name: str = room_cfg[CONF_ROOM_NAME]
        self.trv_entity: str = room_cfg[CONF_TRV_ENTITY]
        self.temp_sensor: str = room_cfg[CONF_TEMP_SENSOR]
        self.window_sensors: list[str] = room_cfg.get(CONF_WINDOW_SENSORS, []) or []
        self.room_switch: str | None = room_cfg.get(CONF_ROOM_SWITCH) or None
        self.sensor_mode_entity: str | None = room_cfg.get(CONF_SENSOR_MODE_ENTITY) or None
        self.check_interval: int = room_cfg.get(CONF_CHECK_INTERVAL, DEFAULT_CHECK_INTERVAL)

        trv_name = self.trv_entity.split(".", 1)[1]
        self.ext_temp_entity: str = f"number.{trv_name}_external_temperature_input"

        self.sensor_mode_set: bool = False
        self.window_open: bool = False
        self.needs_heat: bool = False
        self.previous_hvac_mode: str | None = None
        self.previous_temperature: float | None = None
        self.last_pushed_temp: float | None = None

    def _get_notification_service(self) -> str:
        """Get notification service from global config."""
        global_cfg = self.hass.data.get(DOMAIN, {}).get("global", {})
        return global_cfg.get(
            CONF_NOTIFICATION_SERVICE, DEFAULT_NOTIFICATION_SERVICE
        )

    async def async_update(self) -> None:
        try:
            windows_open = self._check_windows()
            if windows_open and not self.window_open:
                await self._async_handle_window_opened()
            elif not windows_open and self.window_open:
                await self._async_handle_window_closed()
            if not windows_open:
                await self.async_push_external_temp()
        except Exception:
            _LOGGER.exception("Error updating room '%s'", self.name)

    def _check_windows(self) -> bool:
        for sensor_id in self.window_sensors:
            try:
                state = self.hass.states.get(sensor_id)
                if state is not None and state.state == "on":
                    return True
            except Exception:
                _LOGGER.exception(
                    "Room '%s': error reading window sensor %s",
                    self.name, sensor_id,
                )
        return False

    async def _async_handle_window_opened(self) -> None:
        _LOGGER.info("Room '%s': window opened, turning off heating", self.name)
        try:
            trv_state = self.hass.states.get(self.trv_entity)
            if trv_state is not None:
                self.previous_hvac_mode = trv_state.state
                self.previous_temperature = trv_state.attributes.get("temperature")
            else:
                self.previous_hvac_mode = "heat"
                self.previous_temperature = None
        except Exception:
            self.previous_hvac_mode = "heat"
            self.previous_temperature = None

        try:
            await self.hass.services.async_call(
                "climate", "set_hvac_mode",
                {"entity_id": self.trv_entity, "hvac_mode": "off"},
            )
        except Exception:
            _LOGGER.exception("Room '%s': error turning off TRV", self.name)

        self.window_open = True
        await self._async_send_notification(
            f"Room '{self.name}': window opened, heating turned off."
        )

    async def _async_handle_window_closed(self) -> None:
        _LOGGER.info("Room '%s': window closed, restoring heating", self.name)
        try:
            mode = self.previous_hvac_mode
            if not mode or mode == "off":
                mode = "heat"
            await self.hass.services.async_call(
                "climate", "set_hvac_mode",
                {"entity_id": self.trv_entity, "hvac_mode": mode},
            )
            if self.previous_temperature is not None:
                await self.hass.services.async_call(
                    "climate", "set_temperature",
                    {"entity_id": self.trv_entity, "temperature": self.previous_temperature},
                )
        except Exception:
            _LOGGER.exception("Room '%s': error restoring TRV state", self.name)

        self.window_open = False
        self.previous_hvac_mode = None
        self.previous_temperature = None
        await self._async_send_notification(
            f"Room '{self.name}': window closed, heating restored."
        )

    async def _async_ensure_external_sensor_mode(self) -> None:
        if self.sensor_mode_set or not self.sensor_mode_entity:
            return
        try:
            state = self.hass.states.get(self.sensor_mode_entity)
            if state is None:
                self.sensor_mode_set = True
                return
            if state.state == "external":
                self.sensor_mode_set = True
                return
            _LOGGER.info(
                "Room '%s': setting %s to 'external'",
                self.name, self.sensor_mode_entity,
            )
            await self.hass.services.async_call(
                "select", "select_option",
                {"entity_id": self.sensor_mode_entity, "option": "external"},
            )
            self.sensor_mode_set = True
        except Exception:
            _LOGGER.exception(
                "Room '%s': error setting sensor mode", self.name
            )

    async def async_push_external_temp(self) -> None:
        await self._async_ensure_external_sensor_mode()
        try:
            ext_state = self.hass.states.get(self.temp_sensor)
            if ext_state is None or ext_state.state in ("unknown", "unavailable"):
                return
            temp = round(float(ext_state.state), 1)
        except (ValueError, TypeError):
            return

        if temp == self.last_pushed_temp:
            return

        try:
            await self.hass.services.async_call(
                "number", "set_value",
                {"entity_id": self.ext_temp_entity, "value": temp},
            )
            self.last_pushed_temp = temp
        except Exception:
            _LOGGER.exception(
                "Room '%s': error pushing temp to %s",
                self.name, self.ext_temp_entity,
            )

    async def _async_send_notification(self, message: str) -> None:
        try:
            service = self._get_notification_service()
            parts = service.rsplit(".", 1)
            if len(parts) != 2:
                return
            domain, svc = parts
            await self.hass.services.async_call(
                domain, svc,
                {"title": "Heating Manager", "message": message},
            )
        except Exception:
            _LOGGER.exception("Room '%s': error sending notification", self.name)

    def check_heat_demand(self) -> None:
        if self.window_open:
            self.needs_heat = False
            return
        try:
            trv_state = self.hass.states.get(self.trv_entity)
            if trv_state is None:
                self.needs_heat = False
                return
            hvac_action = trv_state.attributes.get("hvac_action")
            if hvac_action is not None:
                self.needs_heat = hvac_action == "heating"
                return
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
            self.needs_heat = False

    async def async_update_room_switch(self) -> None:
        if not self.room_switch:
            return
        try:
            current_state = self.hass.states.get(self.room_switch)
            if current_state is None:
                return
            is_on = current_state.state == "on"
            domain = self.room_switch.split(".", 1)[0]
            if self.needs_heat and not is_on:
                await self.hass.services.async_call(
                    domain, "turn_on", {"entity_id": self.room_switch}
                )
            elif not self.needs_heat and is_on:
                await self.hass.services.async_call(
                    domain, "turn_off", {"entity_id": self.room_switch}
                )
        except Exception:
            _LOGGER.exception(
                "Room '%s': error updating room switch", self.name
            )


def _get_all_rooms(hass: HomeAssistant) -> list[Room]:
    """Collect all Room objects from all room entries."""
    rooms = []
    for data in hass.data.get(DOMAIN, {}).get("rooms", {}).values():
        rooms.append(data["room"])
    return rooms


async def _async_update_cv_switches(hass: HomeAssistant) -> None:
    """Update CV boiler switches based on heat demand across all rooms."""
    global_cfg = hass.data.get(DOMAIN, {}).get("global", {})
    rooms = _get_all_rooms(hass)
    any_needs_heat = any(r.needs_heat for r in rooms)

    for key in (CONF_CV_SWITCH_1, CONF_CV_SWITCH_2):
        switch_entity = global_cfg.get(key)
        if not switch_entity:
            continue
        try:
            current_state = hass.states.get(switch_entity)
            if current_state is None:
                continue
            is_on = current_state.state == "on"
            domain = switch_entity.split(".", 1)[0]
            if any_needs_heat and not is_on:
                await hass.services.async_call(
                    domain, "turn_on", {"entity_id": switch_entity}
                )
            elif not any_needs_heat and is_on:
                await hass.services.async_call(
                    domain, "turn_off", {"entity_id": switch_entity}
                )
        except Exception:
            _LOGGER.exception("Error updating CV switch %s", switch_entity)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up a config entry (global or room)."""
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN].setdefault("rooms", {})

    entry_type = entry.data.get(CONF_ENTRY_TYPE)

    # ── Global entry ──
    if entry_type == ENTRY_TYPE_GLOBAL:
        hass.data[DOMAIN]["global"] = dict(entry.data)
        entry.async_on_unload(
            entry.add_update_listener(_async_update_listener)
        )
        _LOGGER.info("Simple Heating Manager global settings loaded")
        return True

    # ── Room entry ──
    room_cfg = dict(entry.data)
    room = Room(hass, room_cfg)
    unsubs: list = []

    def make_sensor_handler(r: Room):
        async def _handle(event: Event) -> None:
            new_state = event.data.get("new_state")
            if new_state is None or new_state.state in ("unknown", "unavailable"):
                return
            await r.async_push_external_temp()
            r.check_heat_demand()
            await r.async_update_room_switch()
            await _async_update_cv_switches(hass)
        return _handle

    unsubs.append(async_track_state_change_event(
        hass, [room.temp_sensor], make_sensor_handler(room)
    ))

    if room.window_sensors:
        def make_window_handler(r: Room):
            async def _handle(event: Event) -> None:
                new_state = event.data.get("new_state")
                if new_state is None or new_state.state in ("unknown", "unavailable"):
                    return
                await r.async_update()
                r.check_heat_demand()
                await r.async_update_room_switch()
                await _async_update_cv_switches(hass)
            return _handle

        unsubs.append(async_track_state_change_event(
            hass, room.window_sensors, make_window_handler(room)
        ))

    def make_update(r: Room):
        async def _update(_now=None):
            await r.async_update()
            r.check_heat_demand()
            await r.async_update_room_switch()
            await _async_update_cv_switches(hass)
        return _update

    unsubs.append(async_track_time_interval(
        hass, make_update(room), timedelta(seconds=room.check_interval)
    ))

    # Hourly sensor mode check
    async def _hourly_check(_now=None):
        room.sensor_mode_set = False
        await room._async_ensure_external_sensor_mode()

    unsubs.append(async_track_time_interval(
        hass, _hourly_check, timedelta(hours=1)
    ))

    # Initial push
    await room._async_ensure_external_sensor_mode()
    await room.async_push_external_temp()

    hass.data[DOMAIN]["rooms"][entry.entry_id] = {
        "room": room,
        "unsubs": unsubs,
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    entry.async_on_unload(
        entry.add_update_listener(_async_update_listener)
    )

    _LOGGER.info(
        "Room '%s' started (TRV: %s, sensor: %s)",
        room.name, room.trv_entity, room.temp_sensor,
    )
    return True


async def _async_update_listener(
    hass: HomeAssistant, entry: ConfigEntry
) -> None:
    """Handle options update — reload the entry."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    entry_type = entry.data.get(CONF_ENTRY_TYPE)

    if entry_type == ENTRY_TYPE_GLOBAL:
        hass.data.get(DOMAIN, {}).pop("global", None)
        _LOGGER.info("Simple Heating Manager global settings unloaded")
        return True

    # Room entry
    await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    room_data = hass.data.get(DOMAIN, {}).get("rooms", {}).pop(entry.entry_id, None)
    if room_data:
        for unsub in room_data.get("unsubs", []):
            unsub()

    _LOGGER.info("Room '%s' unloaded", entry.data.get(CONF_ROOM_NAME, "?"))
    return True
