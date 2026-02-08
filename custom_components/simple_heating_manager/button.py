"""Button platform for Simple Heating Manager.

Provides a button per room to force the TRV sensor mode to 'external'.
"""

from __future__ import annotations

import logging

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import CONF_ENTRY_TYPE, DOMAIN, ENTRY_TYPE_ROOM

_LOGGER = logging.getLogger(__name__)


def _device_info(entry: ConfigEntry, room) -> DeviceInfo:
    return DeviceInfo(
        identifiers={(DOMAIN, entry.entry_id)},
        name=room.name,
        manufacturer="Simple Heating Manager",
        model="Room",
    )


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
    if room.sensor_mode_entity:
        entities.append(PushExternalSensorButton(entry, room))

    async_add_entities(entities)


class PushExternalSensorButton(ButtonEntity):
    """Button to force TRV sensor mode to 'external'."""

    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_icon = "mdi:upload"

    def __init__(self, entry: ConfigEntry, room) -> None:
        self._room = room
        self._attr_unique_id = f"{entry.entry_id}_push_external"
        self._attr_name = "Push external sensor"
        self._attr_device_info = _device_info(entry, room)

    async def async_press(self) -> None:
        room = self._room
        entity_id = room.sensor_mode_entity

        if not entity_id:
            _LOGGER.warning(
                "Room '%s': no sensor mode entity configured", room.name
            )
            return

        state = self.hass.states.get(entity_id)
        if state is None:
            _LOGGER.warning(
                "Room '%s': sensor mode entity %s not found",
                room.name,
                entity_id,
            )
            return

        if state.state == "external":
            _LOGGER.info(
                "Room '%s': sensor mode already 'external'", room.name
            )
            return

        _LOGGER.info(
            "Room '%s': pushing sensor mode from '%s' to 'external' on %s",
            room.name,
            state.state,
            entity_id,
        )
        await self.hass.services.async_call(
            "select",
            "select_option",
            {"entity_id": entity_id, "option": "external"},
        )
