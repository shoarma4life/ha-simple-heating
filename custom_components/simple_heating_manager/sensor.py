"""Sensor platform for Simple Heating Manager.

Creates sensors per room so rooms appear as devices
under the integration hub with useful information.
"""

from __future__ import annotations

from datetime import timedelta

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_time_interval

from .const import DOMAIN


def _device_info(entry: ConfigEntry, room) -> DeviceInfo:
    """Return shared DeviceInfo for a room."""
    return DeviceInfo(
        identifiers={(DOMAIN, f"{entry.entry_id}_{room.name}")},
        name=room.name,
        manufacturer="Simple Heating Manager",
        model="Room",
    )


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up room sensors."""
    data = hass.data[DOMAIN][entry.entry_id]
    rooms = data["rooms"]

    entities = []
    for room in rooms:
        entities.append(RoomStatusSensor(entry, room))
        entities.append(RoomTrvTemperatureSensor(entry, room))
        entities.append(RoomTargetTemperatureSensor(entry, room))
        entities.append(RoomExternalTemperatureSensor(entry, room))
        entities.append(RoomSensorModeSensor(entry, room))

    async_add_entities(entities)


class RoomStatusSensor(SensorEntity):
    """Sensor showing room heating status."""

    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_icon = "mdi:thermostat"

    def __init__(self, entry: ConfigEntry, room) -> None:
        """Initialize the sensor."""
        self._room = room
        self._attr_unique_id = f"{entry.entry_id}_{room.name}_status"
        self._attr_name = "Status"
        self._attr_native_value = "Idle"
        self._attr_device_info = _device_info(entry, room)
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

        attrs = {}
        attrs["trv_entity"] = room.trv_entity
        attrs["temp_sensor"] = room.temp_sensor
        if room.room_switch:
            attrs["room_switch"] = room.room_switch
        if room.last_pushed_temp is not None:
            attrs["last_pushed_temp"] = room.last_pushed_temp

        trv_state = self.hass.states.get(room.trv_entity)
        if trv_state is not None:
            attrs["hvac_action"] = trv_state.attributes.get(
                "hvac_action", trv_state.state
            )

        self._attr_extra_state_attributes = attrs
        self.async_write_ha_state()


class RoomTrvTemperatureSensor(SensorEntity):
    """Sensor showing TRV current temperature."""

    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_icon = "mdi:thermometer"

    def __init__(self, entry: ConfigEntry, room) -> None:
        """Initialize the sensor."""
        self._room = room
        self._attr_unique_id = f"{entry.entry_id}_{room.name}_trv_temp"
        self._attr_name = "TRV temperature"
        self._attr_device_info = _device_info(entry, room)
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
        """Update from TRV state."""
        trv_state = self.hass.states.get(self._room.trv_entity)
        if trv_state is not None:
            current = trv_state.attributes.get("current_temperature")
            if current is not None:
                try:
                    self._attr_native_value = round(float(current), 1)
                except (ValueError, TypeError):
                    self._attr_native_value = None
            else:
                self._attr_native_value = None
        else:
            self._attr_native_value = None
        self.async_write_ha_state()


class RoomTargetTemperatureSensor(SensorEntity):
    """Sensor showing TRV target temperature."""

    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_icon = "mdi:thermometer-chevron-up"

    def __init__(self, entry: ConfigEntry, room) -> None:
        """Initialize the sensor."""
        self._room = room
        self._attr_unique_id = f"{entry.entry_id}_{room.name}_target_temp"
        self._attr_name = "Target temperature"
        self._attr_device_info = _device_info(entry, room)
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
        """Update from TRV state."""
        trv_state = self.hass.states.get(self._room.trv_entity)
        if trv_state is not None:
            target = trv_state.attributes.get("temperature")
            if target is not None:
                try:
                    self._attr_native_value = round(float(target), 1)
                except (ValueError, TypeError):
                    self._attr_native_value = None
            else:
                self._attr_native_value = None
        else:
            self._attr_native_value = None
        self.async_write_ha_state()


class RoomExternalTemperatureSensor(SensorEntity):
    """Sensor showing external temperature sensor reading."""

    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_icon = "mdi:thermometer-lines"

    def __init__(self, entry: ConfigEntry, room) -> None:
        """Initialize the sensor."""
        self._room = room
        self._attr_unique_id = f"{entry.entry_id}_{room.name}_ext_temp"
        self._attr_name = "External temperature"
        self._attr_device_info = _device_info(entry, room)
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
        """Update from external sensor."""
        sensor_state = self.hass.states.get(self._room.temp_sensor)
        if sensor_state is not None and sensor_state.state not in (
            "unknown", "unavailable",
        ):
            try:
                self._attr_native_value = round(
                    float(sensor_state.state), 1
                )
            except (ValueError, TypeError):
                self._attr_native_value = None
        else:
            self._attr_native_value = None
        self.async_write_ha_state()


class RoomSensorModeSensor(SensorEntity):
    """Sensor showing TRV sensor mode (internal/external)."""

    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_icon = "mdi:swap-horizontal"

    def __init__(self, entry: ConfigEntry, room) -> None:
        """Initialize the sensor."""
        self._room = room
        self._attr_unique_id = f"{entry.entry_id}_{room.name}_sensor_mode"
        self._attr_name = "Sensor mode"
        self._attr_device_info = _device_info(entry, room)
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
        """Update from sensor mode entity."""
        mode_state = self.hass.states.get(self._room.sensor_mode_entity)
        if mode_state is not None and mode_state.state not in (
            "unknown", "unavailable",
        ):
            self._attr_native_value = mode_state.state
        else:
            self._attr_native_value = None
        self.async_write_ha_state()
