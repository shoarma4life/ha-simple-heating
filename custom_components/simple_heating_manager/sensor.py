"""Sensor platform for Simple Heating Manager.

Creates sensors per room so rooms appear as devices under the integration hub.

Entity categories control how HA groups them on the device page:
- Controls (no category): Status, Window, Room switch
- Diagnostic: TRV temperature, Target, External, Sensor mode, Battery
"""

from __future__ import annotations

from datetime import timedelta
import logging

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory, UnitOfTemperature
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_time_interval

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


def _device_info(entry: ConfigEntry, room) -> DeviceInfo:
    """Return shared DeviceInfo for a room."""
    return DeviceInfo(
        identifiers={(DOMAIN, f"{entry.entry_id}_{room.name}")},
        name=room.name,
        manufacturer="Simple Heating Manager",
        model="Room",
    )


def _find_battery_entity(hass: HomeAssistant, trv_entity_id: str) -> str | None:
    """Find the battery sensor for the same device as the TRV."""
    ent_reg = er.async_get(hass)

    # Look up the TRV in the entity registry
    trv_entry = ent_reg.async_get(trv_entity_id)
    if trv_entry is None or trv_entry.device_id is None:
        return None

    # Find all entities on the same device
    for entity in er.async_entries_for_device(ent_reg, trv_entry.device_id):
        device_class = entity.original_device_class or entity.device_class
        if device_class == SensorDeviceClass.BATTERY:
            return entity.entity_id

    return None


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
        # Controls section
        entities.append(RoomStatusSensor(entry, room))
        if room.window_sensors:
            entities.append(RoomWindowSensor(entry, room))
        if room.room_switch:
            entities.append(RoomSwitchStateSensor(entry, room))

        # Diagnostic section
        entities.append(RoomTrvTemperatureSensor(entry, room))
        entities.append(RoomTargetTemperatureSensor(entry, room))
        entities.append(RoomExternalTemperatureSensor(entry, room))
        if room.sensor_mode_entity:
            entities.append(RoomSensorModeSensor(entry, room))

        # Battery: find via device registry
        battery_entity = _find_battery_entity(hass, room.trv_entity)
        if battery_entity:
            entities.append(RoomBatterySensor(entry, room, battery_entity))
        else:
            _LOGGER.debug(
                "Room '%s': no battery entity found for %s",
                room.name,
                room.trv_entity,
            )

    async_add_entities(entities)


# ── Controls (no entity_category) ─────────────────────────────


class RoomStatusSensor(SensorEntity):
    """Sensor showing room heating status."""

    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_icon = "mdi:thermostat"

    def __init__(self, entry: ConfigEntry, room) -> None:
        self._room = room
        self._attr_unique_id = f"{entry.entry_id}_{room.name}_status"
        self._attr_name = "Status"
        self._attr_native_value = "Idle"
        self._attr_device_info = _device_info(entry, room)
        self._unsub = None

    async def async_added_to_hass(self) -> None:
        self._unsub = async_track_time_interval(
            self.hass, self._update_state, timedelta(seconds=30)
        )
        self._update_state()

    async def async_will_remove_from_hass(self) -> None:
        if self._unsub:
            self._unsub()

    @callback
    def _update_state(self, _now=None) -> None:
        room = self._room
        if room.window_open:
            status = "Window open"
        elif room.needs_heat:
            status = "Heating"
        else:
            status = "Idle"

        self._attr_native_value = status
        attrs = {"trv_entity": room.trv_entity, "temp_sensor": room.temp_sensor}
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


class RoomWindowSensor(SensorEntity):
    """Sensor showing window open/closed status."""

    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_icon = "mdi:window-closed-variant"

    def __init__(self, entry: ConfigEntry, room) -> None:
        self._room = room
        self._attr_unique_id = f"{entry.entry_id}_{room.name}_window"
        self._attr_name = "Window"
        self._attr_native_value = "Closed"
        self._attr_device_info = _device_info(entry, room)
        self._unsub = None

    async def async_added_to_hass(self) -> None:
        self._unsub = async_track_time_interval(
            self.hass, self._update_state, timedelta(seconds=30)
        )
        self._update_state()

    async def async_will_remove_from_hass(self) -> None:
        if self._unsub:
            self._unsub()

    @callback
    def _update_state(self, _now=None) -> None:
        any_open = False
        for sensor_id in self._room.window_sensors:
            state = self.hass.states.get(sensor_id)
            if state is not None and state.state == "on":
                any_open = True
                break
        self._attr_native_value = "Open" if any_open else "Closed"
        self._attr_icon = (
            "mdi:window-open-variant" if any_open
            else "mdi:window-closed-variant"
        )
        self.async_write_ha_state()


class RoomSwitchStateSensor(SensorEntity):
    """Sensor showing room switch state (on/off)."""

    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_icon = "mdi:power-plug"

    def __init__(self, entry: ConfigEntry, room) -> None:
        self._room = room
        self._attr_unique_id = f"{entry.entry_id}_{room.name}_switch_state"
        self._attr_name = "Room switch"
        self._attr_device_info = _device_info(entry, room)
        self._unsub = None

    async def async_added_to_hass(self) -> None:
        self._unsub = async_track_time_interval(
            self.hass, self._update_state, timedelta(seconds=30)
        )
        self._update_state()

    async def async_will_remove_from_hass(self) -> None:
        if self._unsub:
            self._unsub()

    @callback
    def _update_state(self, _now=None) -> None:
        state = self.hass.states.get(self._room.room_switch)
        if state is not None and state.state not in ("unknown", "unavailable"):
            self._attr_native_value = state.state.capitalize()
            self._attr_icon = (
                "mdi:power-plug" if state.state == "on"
                else "mdi:power-plug-off"
            )
        else:
            self._attr_native_value = None
        self.async_write_ha_state()


# ── Diagnostic (entity_category = DIAGNOSTIC) ─────────────────


class RoomTrvTemperatureSensor(SensorEntity):
    """Sensor showing TRV current temperature."""

    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_icon = "mdi:thermometer"

    def __init__(self, entry: ConfigEntry, room) -> None:
        self._room = room
        self._attr_unique_id = f"{entry.entry_id}_{room.name}_trv_temp"
        self._attr_name = "TRV temperature"
        self._attr_device_info = _device_info(entry, room)
        self._unsub = None

    async def async_added_to_hass(self) -> None:
        self._unsub = async_track_time_interval(
            self.hass, self._update_state, timedelta(seconds=30)
        )
        self._update_state()

    async def async_will_remove_from_hass(self) -> None:
        if self._unsub:
            self._unsub()

    @callback
    def _update_state(self, _now=None) -> None:
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
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_icon = "mdi:thermometer-chevron-up"

    def __init__(self, entry: ConfigEntry, room) -> None:
        self._room = room
        self._attr_unique_id = f"{entry.entry_id}_{room.name}_target_temp"
        self._attr_name = "Target temperature"
        self._attr_device_info = _device_info(entry, room)
        self._unsub = None

    async def async_added_to_hass(self) -> None:
        self._unsub = async_track_time_interval(
            self.hass, self._update_state, timedelta(seconds=30)
        )
        self._update_state()

    async def async_will_remove_from_hass(self) -> None:
        if self._unsub:
            self._unsub()

    @callback
    def _update_state(self, _now=None) -> None:
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
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_icon = "mdi:thermometer-lines"

    def __init__(self, entry: ConfigEntry, room) -> None:
        self._room = room
        self._attr_unique_id = f"{entry.entry_id}_{room.name}_ext_temp"
        self._attr_name = "External temperature"
        self._attr_device_info = _device_info(entry, room)
        self._unsub = None

    async def async_added_to_hass(self) -> None:
        self._unsub = async_track_time_interval(
            self.hass, self._update_state, timedelta(seconds=30)
        )
        self._update_state()

    async def async_will_remove_from_hass(self) -> None:
        if self._unsub:
            self._unsub()

    @callback
    def _update_state(self, _now=None) -> None:
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
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:swap-horizontal"

    def __init__(self, entry: ConfigEntry, room) -> None:
        self._room = room
        self._attr_unique_id = f"{entry.entry_id}_{room.name}_sensor_mode"
        self._attr_name = "Sensor mode"
        self._attr_device_info = _device_info(entry, room)
        self._unsub = None

    async def async_added_to_hass(self) -> None:
        self._unsub = async_track_time_interval(
            self.hass, self._update_state, timedelta(seconds=30)
        )
        self._update_state()

    async def async_will_remove_from_hass(self) -> None:
        if self._unsub:
            self._unsub()

    @callback
    def _update_state(self, _now=None) -> None:
        mode_state = self.hass.states.get(self._room.sensor_mode_entity)
        if mode_state is not None and mode_state.state not in (
            "unknown", "unavailable",
        ):
            self._attr_native_value = mode_state.state
        else:
            self._attr_native_value = None
        self.async_write_ha_state()


class RoomBatterySensor(SensorEntity):
    """Sensor showing TRV battery percentage."""

    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_device_class = SensorDeviceClass.BATTERY
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = "%"

    def __init__(self, entry: ConfigEntry, room, battery_entity_id: str) -> None:
        self._room = room
        self._battery_entity = battery_entity_id
        self._attr_unique_id = f"{entry.entry_id}_{room.name}_battery"
        self._attr_name = "TRV battery"
        self._attr_device_info = _device_info(entry, room)
        self._unsub = None

    async def async_added_to_hass(self) -> None:
        self._unsub = async_track_time_interval(
            self.hass, self._update_state, timedelta(seconds=300)
        )
        self._update_state()

    async def async_will_remove_from_hass(self) -> None:
        if self._unsub:
            self._unsub()

    @callback
    def _update_state(self, _now=None) -> None:
        state = self.hass.states.get(self._battery_entity)
        if state is not None and state.state not in (
            "unknown", "unavailable",
        ):
            try:
                self._attr_native_value = round(float(state.state))
            except (ValueError, TypeError):
                self._attr_native_value = None
        else:
            self._attr_native_value = None
        self.async_write_ha_state()
