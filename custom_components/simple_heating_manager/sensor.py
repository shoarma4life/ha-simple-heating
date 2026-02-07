"""Sensor platform for Simple Heating Manager.

Creates a status sensor per room so rooms appear as devices
under the integration hub.
"""

from __future__ import annotations

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_time_interval

from datetime import timedelta

from .const import DOMAIN


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up room status sensors."""
    data = hass.data[DOMAIN][entry.entry_id]
    rooms = data["rooms"]

    entities = []
    for room in rooms:
        entities.append(RoomStatusSensor(hass, entry, room))

    async_add_entities(entities)


class RoomStatusSensor(SensorEntity):
    """Sensor showing room heating status."""

    _attr_has_entity_name = True
    _attr_icon = "mdi:thermostat"

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, room) -> None:
        """Initialize the sensor."""
        self._room = room
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_{room.name}_status"
        self._attr_name = "Status"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, f"{entry.entry_id}_{room.name}")},
            "name": room.name,
            "manufacturer": "Simple Heating Manager",
            "model": "Room",
            "via_device": (DOMAIN, entry.entry_id),
        }
        self._unsub = None

    async def async_added_to_hass(self) -> None:
        """Start periodic updates when added."""
        self._unsub = async_track_time_interval(
            self.hass, self._update_state, timedelta(seconds=30)
        )
        self._update_state()

    async def async_will_remove_from_hass(self) -> None:
        """Clean up on removal."""
        if self._unsub:
            self._unsub()

    @callback
    def _update_state(self, _now=None) -> None:
        """Update sensor state from room data."""
        room = self._room

        if room.window_open:
            status = "Window open"
        elif room.needs_heat:
            status = "Heating"
        else:
            status = "Idle"

        self._attr_native_value = status

        # Build extra attributes
        attrs = {}

        trv_state = self.hass.states.get(room.trv_entity)
        if trv_state is not None:
            current = trv_state.attributes.get("current_temperature")
            target = trv_state.attributes.get("temperature")
            if current is not None:
                attrs["trv_temperature"] = current
            if target is not None:
                attrs["trv_target"] = target
            attrs["hvac_action"] = trv_state.attributes.get("hvac_action", trv_state.state)

        sensor_state = self.hass.states.get(room.temp_sensor)
        if sensor_state is not None and sensor_state.state not in ("unknown", "unavailable"):
            try:
                attrs["external_temperature"] = round(float(sensor_state.state), 1)
            except (ValueError, TypeError):
                pass

        mode_state = self.hass.states.get(room.sensor_mode_entity)
        if mode_state is not None:
            attrs["sensor_mode"] = mode_state.state

        if room.last_pushed_temp is not None:
            attrs["last_pushed_temp"] = room.last_pushed_temp

        attrs["trv_entity"] = room.trv_entity
        attrs["temp_sensor"] = room.temp_sensor

        self._attr_extra_state_attributes = attrs
        self.async_write_ha_state()
