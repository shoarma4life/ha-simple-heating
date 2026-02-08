"""Sensor platform for Simple Heating Manager.

Each room entry creates sensors grouped by entity_category:
- Controls: Window, Room switch
- Diagnostic: TRV temperature, Target, External, Sensor mode, Batteries
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


def _find_battery_entity(hass: HomeAssistant, entity_id: str) -> str | None:
    """Find battery entity on the same device as the given entity."""
    ent_reg = er.async_get(hass)
    ent_entry = ent_reg.async_get(entity_id)
    if ent_entry is None:
        _LOGGER.debug("Battery lookup: %s not in entity registry", entity_id)
        return None
    if ent_entry.device_id is None:
        _LOGGER.debug("Battery lookup: %s has no device_id", entity_id)
        return None

    device_entities = er.async_entries_for_device(ent_reg, ent_entry.device_id)
    _LOGGER.debug(
        "Battery lookup: %s device %s has %d entities",
        entity_id, ent_entry.device_id, len(device_entities),
    )

    for entity in device_entities:
        dc = entity.original_device_class or entity.device_class
        if dc is not None and str(dc) == "battery":
            _LOGGER.debug(
                "Battery lookup: found %s (device_class=battery) for %s",
                entity.entity_id, entity_id,
            )
            return entity.entity_id

    for entity in device_entities:
        if "battery" in entity.entity_id:
            _LOGGER.debug(
                "Battery lookup: found %s (name match) for %s",
                entity.entity_id, entity_id,
            )
            return entity.entity_id

    _LOGGER.debug("Battery lookup: no battery entity found for %s", entity_id)
    return None


def _find_battery_entities(
    hass: HomeAssistant, entity_ids: list[str]
) -> list[str]:
    """Find battery entities for a list of entities (deduplicated)."""
    seen: set[str] = set()
    result: list[str] = []
    for eid in entity_ids:
        bat = _find_battery_entity(hass, eid)
        if bat and bat not in seen:
            seen.add(bat)
            result.append(bat)
    return result


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
    entities.append(RoomSourceEntitySensor(
        entry, room, room.temp_sensor, "Temperature sensor", "src_temp",
        "mdi:thermometer-probe",
    ))
    if room.window_sensors:
        entities.append(RoomSourceEntitySensor(
            entry, room,
            ", ".join(room.window_sensors),
            "Window sensors", "src_window",
            "mdi:window-closed-variant",
        ))

    # Batteries
    trv_battery = _find_battery_entity(hass, room.trv_entity)
    if trv_battery:
        entities.append(RoomBatterySensor(
            entry, room, trv_battery, "TRV battery", "trv_battery",
        ))

    sensor_battery = _find_battery_entity(hass, room.temp_sensor)
    if sensor_battery:
        entities.append(RoomBatterySensor(
            entry, room, sensor_battery, "Sensor battery", "sensor_battery",
        ))

    if room.window_sensors:
        window_batteries = _find_battery_entities(hass, room.window_sensors)
        if window_batteries:
            entities.append(RoomMultiBatterySensor(
                entry, room, window_batteries, "Window battery", "window_battery",
            ))

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


# ── Source entity references ───────────────────────────────────


class RoomSourceEntitySensor(SensorEntity):
    """Static sensor showing a configured source entity ID."""

    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(
        self, entry, room, value: str, name: str, uid_suffix: str, icon: str,
    ):
        self._attr_unique_id = f"{entry.entry_id}_{uid_suffix}"
        self._attr_name = name
        self._attr_native_value = value
        self._attr_icon = icon
        self._attr_device_info = _device_info(entry, room)


# ── Battery sensors ────────────────────────────────────────────


class RoomBatterySensor(SensorEntity):
    """Battery sensor tracking a single source entity."""

    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_device_class = SensorDeviceClass.BATTERY
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = "%"

    def __init__(
        self, entry, room, battery_entity_id: str, name: str, uid_suffix: str
    ):
        self._room = room
        self._battery_entity = battery_entity_id
        self._attr_unique_id = f"{entry.entry_id}_{uid_suffix}"
        self._attr_name = name
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


class RoomMultiBatterySensor(SensorEntity):
    """Battery sensor tracking multiple sources, reports the lowest value."""

    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_device_class = SensorDeviceClass.BATTERY
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = "%"

    def __init__(
        self, entry, room, battery_entity_ids: list[str],
        name: str, uid_suffix: str,
    ):
        self._room = room
        self._battery_entities = battery_entity_ids
        self._attr_unique_id = f"{entry.entry_id}_{uid_suffix}"
        self._attr_name = name
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
        values = []
        for eid in self._battery_entities:
            s = self.hass.states.get(eid)
            if s is not None and s.state not in ("unknown", "unavailable"):
                try:
                    values.append(round(float(s.state)))
                except (ValueError, TypeError):
                    pass
        self._attr_native_value = min(values) if values else None
        self.async_write_ha_state()
