"""Sensor platform for Simple Heating Manager.

Each room entry creates sensors grouped by entity_category:
- Controls: Window, Room switch
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

from .const import CONF_ENTRY_TYPE, DOMAIN, ENTRY_TYPE_ROOM

_LOGGER = logging.getLogger(__name__)


def _device_info(entry: ConfigEntry, room) -> DeviceInfo:
    return DeviceInfo(
        identifiers={(DOMAIN, entry.entry_id)},
        name=room.name,
        manufacturer="Simple Heating Manager",
        model="Room",
    )


def _find_battery_entity(hass: HomeAssistant, trv_entity_id: str) -> str | None:
    ent_reg = er.async_get(hass)
    trv_entry = ent_reg.async_get(trv_entity_id)
    if trv_entry is None or trv_entry.device_id is None:
        return None

    device_entities = er.async_entries_for_device(ent_reg, trv_entry.device_id)

    for entity in device_entities:
        dc = entity.original_device_class or entity.device_class
        if dc is not None and str(dc) == "battery":
            return entity.entity_id

    for entity in device_entities:
        if "battery" in entity.entity_id:
            return entity.entity_id

    return None


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    if entry.data.get(CONF_ENTRY_TYPE) != ENTRY_TYPE_ROOM:
        return

    room_data = hass.data[DOMAIN]["rooms"].get(entry.entry_id)
    if not room_data:
        return
    room = room_data["room"]

    entities = []

    # Controls
    if room.window_sensors:
        entities.append(RoomWindowSensor(entry, room))
    if room.room_switch:
        entities.append(RoomSwitchStateSensor(entry, room))

    # Diagnostic
    entities.append(RoomTrvTemperatureSensor(entry, room))
    entities.append(RoomTargetTemperatureSensor(entry, room))
    entities.append(RoomExternalTemperatureSensor(entry, room))
    if room.sensor_mode_entity:
        entities.append(RoomSensorModeSensor(entry, room))

    battery_entity = _find_battery_entity(hass, room.trv_entity)
    if battery_entity:
        entities.append(RoomBatterySensor(entry, room, battery_entity))

    async_add_entities(entities)


# ── Controls ───────────────────────────────────────────────────


class RoomWindowSensor(SensorEntity):
    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_icon = "mdi:window-closed-variant"

    def __init__(self, entry, room):
        self._room = room
        self._attr_unique_id = f"{entry.entry_id}_window"
        self._attr_name = "Window"
        self._attr_native_value = "Closed"
        self._attr_device_info = _device_info(entry, room)
        self._unsub = None

    async def async_added_to_hass(self):
        self._unsub = async_track_time_interval(
            self.hass, self._update_state, timedelta(seconds=30)
        )
        self._update_state()

    async def async_will_remove_from_hass(self):
        if self._unsub:
            self._unsub()

    @callback
    def _update_state(self, _now=None):
        any_open = any(
            (s := self.hass.states.get(sid)) is not None and s.state == "on"
            for sid in self._room.window_sensors
        )
        self._attr_native_value = "Open" if any_open else "Closed"
        self._attr_icon = (
            "mdi:window-open-variant" if any_open
            else "mdi:window-closed-variant"
        )
        self.async_write_ha_state()


class RoomSwitchStateSensor(SensorEntity):
    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_icon = "mdi:power-plug"

    def __init__(self, entry, room):
        self._room = room
        self._attr_unique_id = f"{entry.entry_id}_switch_state"
        self._attr_name = "Room switch"
        self._attr_device_info = _device_info(entry, room)
        self._unsub = None

    async def async_added_to_hass(self):
        self._unsub = async_track_time_interval(
            self.hass, self._update_state, timedelta(seconds=30)
        )
        self._update_state()

    async def async_will_remove_from_hass(self):
        if self._unsub:
            self._unsub()

    @callback
    def _update_state(self, _now=None):
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


# ── Diagnostic ─────────────────────────────────────────────────


class RoomTrvTemperatureSensor(SensorEntity):
    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_icon = "mdi:thermometer"

    def __init__(self, entry, room):
        self._room = room
        self._attr_unique_id = f"{entry.entry_id}_trv_temp"
        self._attr_name = "TRV temperature"
        self._attr_device_info = _device_info(entry, room)
        self._unsub = None

    async def async_added_to_hass(self):
        self._unsub = async_track_time_interval(
            self.hass, self._update_state, timedelta(seconds=30)
        )
        self._update_state()

    async def async_will_remove_from_hass(self):
        if self._unsub:
            self._unsub()

    @callback
    def _update_state(self, _now=None):
        trv = self.hass.states.get(self._room.trv_entity)
        val = None
        if trv is not None:
            c = trv.attributes.get("current_temperature")
            if c is not None:
                try:
                    val = round(float(c), 1)
                except (ValueError, TypeError):
                    pass
        self._attr_native_value = val
        self.async_write_ha_state()


class RoomTargetTemperatureSensor(SensorEntity):
    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_icon = "mdi:thermometer-chevron-up"

    def __init__(self, entry, room):
        self._room = room
        self._attr_unique_id = f"{entry.entry_id}_target_temp"
        self._attr_name = "Target temperature"
        self._attr_device_info = _device_info(entry, room)
        self._unsub = None

    async def async_added_to_hass(self):
        self._unsub = async_track_time_interval(
            self.hass, self._update_state, timedelta(seconds=30)
        )
        self._update_state()

    async def async_will_remove_from_hass(self):
        if self._unsub:
            self._unsub()

    @callback
    def _update_state(self, _now=None):
        trv = self.hass.states.get(self._room.trv_entity)
        val = None
        if trv is not None:
            t = trv.attributes.get("temperature")
            if t is not None:
                try:
                    val = round(float(t), 1)
                except (ValueError, TypeError):
                    pass
        self._attr_native_value = val
        self.async_write_ha_state()


class RoomExternalTemperatureSensor(SensorEntity):
    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_icon = "mdi:thermometer-lines"

    def __init__(self, entry, room):
        self._room = room
        self._attr_unique_id = f"{entry.entry_id}_ext_temp"
        self._attr_name = "External temperature"
        self._attr_device_info = _device_info(entry, room)
        self._unsub = None

    async def async_added_to_hass(self):
        self._unsub = async_track_time_interval(
            self.hass, self._update_state, timedelta(seconds=30)
        )
        self._update_state()

    async def async_will_remove_from_hass(self):
        if self._unsub:
            self._unsub()

    @callback
    def _update_state(self, _now=None):
        s = self.hass.states.get(self._room.temp_sensor)
        val = None
        if s is not None and s.state not in ("unknown", "unavailable"):
            try:
                val = round(float(s.state), 1)
            except (ValueError, TypeError):
                pass
        self._attr_native_value = val
        self.async_write_ha_state()


class RoomSensorModeSensor(SensorEntity):
    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:swap-horizontal"

    def __init__(self, entry, room):
        self._room = room
        self._attr_unique_id = f"{entry.entry_id}_sensor_mode"
        self._attr_name = "Sensor mode"
        self._attr_device_info = _device_info(entry, room)
        self._unsub = None

    async def async_added_to_hass(self):
        self._unsub = async_track_time_interval(
            self.hass, self._update_state, timedelta(seconds=30)
        )
        self._update_state()

    async def async_will_remove_from_hass(self):
        if self._unsub:
            self._unsub()

    @callback
    def _update_state(self, _now=None):
        s = self.hass.states.get(self._room.sensor_mode_entity)
        val = None
        if s is not None and s.state not in ("unknown", "unavailable"):
            val = s.state
        self._attr_native_value = val
        self.async_write_ha_state()


class RoomBatterySensor(SensorEntity):
    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_device_class = SensorDeviceClass.BATTERY
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = "%"

    def __init__(self, entry, room, battery_entity_id: str):
        self._room = room
        self._battery_entity = battery_entity_id
        self._attr_unique_id = f"{entry.entry_id}_battery"
        self._attr_name = "TRV battery"
        self._attr_device_info = _device_info(entry, room)
        self._unsub = None

    async def async_added_to_hass(self):
        self._unsub = async_track_time_interval(
            self.hass, self._update_state, timedelta(seconds=300)
        )
        self._update_state()

    async def async_will_remove_from_hass(self):
        if self._unsub:
            self._unsub()

    @callback
    def _update_state(self, _now=None):
        s = self.hass.states.get(self._battery_entity)
        val = None
        if s is not None and s.state not in ("unknown", "unavailable"):
            try:
                val = round(float(s.state))
            except (ValueError, TypeError):
                pass
        self._attr_native_value = val
        self.async_write_ha_state()
