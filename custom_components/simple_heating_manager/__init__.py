"""Simple Heating Manager - HACS custom integration.

Manages heating per room:
- Pushes external temperature to TRV's external_temperature_input entity
- Controls CV boiler switches based on TRV heat demand
- Window detection: turns off TRV when window opens, restores when closed

Single config entry with global settings (CV switches, notifications)
and a list of rooms.
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
    CONF_NOTIFICATION_SERVICE,
    CONF_ROOM_NAME,
    CONF_ROOMS,
    CONF_TEMP_SENSOR,
    CONF_TRV_ENTITY,
    CONF_WINDOW_SENSORS,
    DEFAULT_CHECK_INTERVAL,
    DEFAULT_NOTIFICATION_SERVICE,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)


class Room:
    """Manages heating logic for a single room."""

    def __init__(self, hass: HomeAssistant, room_cfg: dict, global_cfg: dict) -> None:
        """Initialize room."""
        self.hass = hass

        self.name: str = room_cfg[CONF_ROOM_NAME]
        self.trv_entity: str = room_cfg[CONF_TRV_ENTITY]
        self.temp_sensor: str = room_cfg[CONF_TEMP_SENSOR]
        self.window_sensors: list[str] = room_cfg.get(CONF_WINDOW_SENSORS, []) or []
        self.check_interval: int = room_cfg.get(CONF_CHECK_INTERVAL, DEFAULT_CHECK_INTERVAL)

        self.notification_service: str = global_cfg.get(
            CONF_NOTIFICATION_SERVICE, DEFAULT_NOTIFICATION_SERVICE
        )

        # Derive entities and MQTT topic from TRV name
        # e.g. climate.trv_badkamer -> number.trv_badkamer_external_temperature_input
        #                            -> select.trv_badkamer_sensor
        #                            -> zigbee2mqtt/trv_badkamer/set
        trv_name = self.trv_entity.split(".", 1)[1]
        self.ext_temp_entity: str = f"number.{trv_name}_external_temperature_input"
        self.sensor_mode_entity: str = f"select.{trv_name}_sensor"
        self.mqtt_topic: str = f"zigbee2mqtt/{trv_name}/set"

        self.sensor_mode_set: bool = False
        self.window_open: bool = False
        self.needs_heat: bool = False
        self.previous_hvac_mode: str | None = None
        self.previous_temperature: float | None = None
        self.last_pushed_temp: float | None = None

    async def async_update(self) -> None:
        """Main update cycle for this room."""
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

    async def _async_handle_window_opened(self) -> None:
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
            await self.hass.services.async_call(
                "climate",
                "set_hvac_mode",
                {"entity_id": self.trv_entity, "hvac_mode": "off"},
            )
        except Exception:
            _LOGGER.exception(
                "Room '%s': error turning off TRV", self.name
            )

        self.window_open = True
        await self._async_send_notification(
            f"Room '{self.name}': window opened, heating turned off."
        )

    async def _async_handle_window_closed(self) -> None:
        """Handle window closing: restore previous TRV state."""
        _LOGGER.info(
            "Room '%s': window closed, restoring heating", self.name
        )

        try:
            mode = self.previous_hvac_mode
            if not mode or mode == "off":
                mode = "heat"
            await self.hass.services.async_call(
                "climate",
                "set_hvac_mode",
                {"entity_id": self.trv_entity, "hvac_mode": mode},
            )

            if self.previous_temperature is not None:
                await self.hass.services.async_call(
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

        await self._async_send_notification(
            f"Room '{self.name}': window closed, heating restored."
        )

    async def _async_ensure_external_sensor_mode(self) -> None:
        """Ensure the TRV sensor mode is set to 'external' via MQTT."""
        if self.sensor_mode_set:
            return

        try:
            state = self.hass.states.get(self.sensor_mode_entity)
            if state is not None and state.state == "external":
                self.sensor_mode_set = True
                return

            await self._async_set_sensor_mode_external()
            self.sensor_mode_set = True
        except Exception:
            _LOGGER.exception(
                "Room '%s': error setting sensor mode to external",
                self.name,
            )

    async def _async_set_sensor_mode_external(self) -> None:
        """Set TRV sensor mode to 'external' via direct MQTT publish."""
        _LOGGER.info(
            "Room '%s': setting sensor to 'external' via MQTT (%s)",
            self.name,
            self.mqtt_topic,
        )
        await self.hass.services.async_call(
            "mqtt",
            "publish",
            {
                "topic": self.mqtt_topic,
                "payload": '{"sensor": "external"}',
            },
        )

    async def async_push_external_temp(self) -> None:
        """Push external sensor temperature directly to TRV.

        Reads the external temperature sensor and writes the value to
        number.{trv_name}_external_temperature_input so the TRV knows
        the real room temperature.
        """
        await self._async_ensure_external_sensor_mode()

        try:
            ext_state = self.hass.states.get(self.temp_sensor)
            if ext_state is None or ext_state.state in ("unknown", "unavailable"):
                _LOGGER.warning(
                    "Room '%s': external sensor %s unavailable",
                    self.name,
                    self.temp_sensor,
                )
                return
            temp = round(float(ext_state.state), 1)
        except (ValueError, TypeError):
            _LOGGER.warning(
                "Room '%s': could not read temperature from %s",
                self.name,
                self.temp_sensor,
            )
            return

        if temp == self.last_pushed_temp:
            _LOGGER.debug(
                "Room '%s': temp unchanged (%.1f), skipping",
                self.name,
                temp,
            )
            return

        _LOGGER.info(
            "Room '%s': pushing %.1f°C to %s",
            self.name,
            temp,
            self.ext_temp_entity,
        )

        try:
            await self.hass.services.async_call(
                "number",
                "set_value",
                {"entity_id": self.ext_temp_entity, "value": temp},
            )
            self.last_pushed_temp = temp
        except Exception:
            _LOGGER.exception(
                "Room '%s': error pushing temp to %s",
                self.name,
                self.ext_temp_entity,
            )

    async def _async_send_notification(self, message: str) -> None:
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
            await self.hass.services.async_call(
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
            _LOGGER.exception(
                "Room '%s': error checking heat demand", self.name
            )
            self.needs_heat = False


async def _async_update_cv_switches(
    hass: HomeAssistant, entry: ConfigEntry, rooms: list[Room]
) -> None:
    """Update CV boiler switches based on heat demand across all rooms."""
    any_needs_heat = any(r.needs_heat for r in rooms)

    for key in (CONF_CV_SWITCH_1, CONF_CV_SWITCH_2):
        switch_entity = entry.data.get(key)
        if not switch_entity:
            continue

        try:
            current_state = hass.states.get(switch_entity)
            if current_state is None:
                _LOGGER.warning("CV switch %s not found", switch_entity)
                continue

            is_on = current_state.state == "on"
            domain = switch_entity.split(".", 1)[0]

            if any_needs_heat and not is_on:
                _LOGGER.info("CV switch %s: turning ON (heat demanded)", switch_entity)
                await hass.services.async_call(
                    domain, "turn_on", {"entity_id": switch_entity}
                )
            elif not any_needs_heat and is_on:
                _LOGGER.info(
                    "CV switch %s: turning OFF (no room needs heat)", switch_entity
                )
                await hass.services.async_call(
                    domain, "turn_off", {"entity_id": switch_entity}
                )
        except Exception:
            _LOGGER.exception("Error updating CV switch %s", switch_entity)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Simple Heating Manager from a config entry."""
    rooms_cfg = entry.data.get(CONF_ROOMS, [])
    global_cfg = dict(entry.data)

    rooms: list[Room] = []
    unsubs: list = []

    for room_cfg in rooms_cfg:
        room = Room(hass, room_cfg, global_cfg)
        rooms.append(room)

        # Trigger on external sensor state change (immediate)
        def make_sensor_handler(r: Room):
            async def _handle_sensor_change(event: Event) -> None:
                new_state = event.data.get("new_state")
                if new_state is None or new_state.state in ("unknown", "unavailable"):
                    return
                await r.async_push_external_temp()
                r.check_heat_demand()
                await _async_update_cv_switches(hass, entry, rooms)
            return _handle_sensor_change

        unsub = async_track_state_change_event(
            hass, [room.temp_sensor], make_sensor_handler(room)
        )
        unsubs.append(unsub)

        # Trigger on window sensor state change (immediate open/close)
        if room.window_sensors:
            def make_window_handler(r: Room):
                async def _handle_window_change(event: Event) -> None:
                    new_state = event.data.get("new_state")
                    if new_state is None or new_state.state in ("unknown", "unavailable"):
                        return
                    await r.async_update()
                    r.check_heat_demand()
                    await _async_update_cv_switches(hass, entry, rooms)
                return _handle_window_change

            unsub_win = async_track_state_change_event(
                hass, room.window_sensors, make_window_handler(room)
            )
            unsubs.append(unsub_win)

        # Periodic fallback for window checks and CV switch updates
        def make_update(r: Room):
            async def _update(_now=None):
                await r.async_update()
                r.check_heat_demand()
                await _async_update_cv_switches(hass, entry, rooms)
            return _update

        cancel = async_track_time_interval(
            hass, make_update(room), timedelta(seconds=room.check_interval)
        )
        unsubs.append(cancel)

        _LOGGER.info(
            "Setting up room '%s' (TRV: %s, sensor: %s -> %s, interval: %ds)",
            room.name,
            room.trv_entity,
            room.temp_sensor,
            room.ext_temp_entity,
            room.check_interval,
        )

    # Hourly check: verify all TRVs are still set to external sensor mode
    async def _hourly_sensor_mode_check(_now=None):
        for r in rooms:
            r.sensor_mode_set = False
            await r._async_ensure_external_sensor_mode()

    cancel_hourly = async_track_time_interval(
        hass, _hourly_sensor_mode_check, timedelta(hours=1)
    )
    unsubs.append(cancel_hourly)

    # Run sensor mode check + initial temp push immediately at startup
    for room in rooms:
        await room._async_ensure_external_sensor_mode()
        await room.async_push_external_temp()

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {
        "rooms": rooms,
        "unsubs": unsubs,
    }

    entry.async_on_unload(
        entry.add_update_listener(_async_update_listener)
    )

    _LOGGER.info(
        "Simple Heating Manager started with %d room(s)", len(rooms)
    )
    return True


async def _async_update_listener(
    hass: HomeAssistant, entry: ConfigEntry
) -> None:
    """Handle options update — reload the entry."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload the config entry."""
    data = hass.data[DOMAIN].pop(entry.entry_id, None)
    if data:
        for unsub in data.get("unsubs", []):
            unsub()
    _LOGGER.info("Simple Heating Manager unloaded")
    return True
