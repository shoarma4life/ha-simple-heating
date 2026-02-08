"""Config flow for Simple Heating Manager."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, OptionsFlow
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import selector

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


def _room_schema(defaults: dict | None = None) -> vol.Schema:
    """Build the room configuration schema."""
    d = defaults or {}
    fields: dict = {}

    if CONF_ROOM_NAME in d:
        fields[vol.Required(CONF_ROOM_NAME, default=d[CONF_ROOM_NAME])] = (
            selector.TextSelector()
        )
    else:
        fields[vol.Required(CONF_ROOM_NAME)] = selector.TextSelector()

    if CONF_TRV_ENTITY in d:
        fields[vol.Required(
            CONF_TRV_ENTITY, default=d[CONF_TRV_ENTITY]
        )] = selector.EntitySelector(
            selector.EntitySelectorConfig(domain="climate")
        )
    else:
        fields[vol.Required(CONF_TRV_ENTITY)] = selector.EntitySelector(
            selector.EntitySelectorConfig(domain="climate")
        )

    if CONF_TEMP_SENSOR in d:
        fields[vol.Required(
            CONF_TEMP_SENSOR, default=d[CONF_TEMP_SENSOR]
        )] = selector.EntitySelector(
            selector.EntitySelectorConfig(
                domain="sensor", device_class="temperature"
            )
        )
    else:
        fields[vol.Required(CONF_TEMP_SENSOR)] = selector.EntitySelector(
            selector.EntitySelectorConfig(
                domain="sensor", device_class="temperature"
            )
        )
    fields[vol.Optional(
        CONF_WINDOW_SENSORS,
        description={"suggested_value": d.get(CONF_WINDOW_SENSORS)},
    )] = selector.EntitySelector(
        selector.EntitySelectorConfig(
            domain="binary_sensor", multiple=True
        )
    )
    fields[vol.Optional(
        CONF_SENSOR_MODE_ENTITY,
        description={"suggested_value": d.get(CONF_SENSOR_MODE_ENTITY)},
    )] = selector.EntitySelector(
        selector.EntitySelectorConfig(domain="select")
    )
    fields[vol.Optional(
        CONF_ROOM_SWITCH,
        description={"suggested_value": d.get(CONF_ROOM_SWITCH)},
    )] = selector.EntitySelector(
        selector.EntitySelectorConfig(
            domain=["switch", "input_boolean"]
        )
    )
    fields[vol.Optional(
        CONF_CHECK_INTERVAL,
        default=d.get(CONF_CHECK_INTERVAL, DEFAULT_CHECK_INTERVAL),
    )] = selector.NumberSelector(
        selector.NumberSelectorConfig(
            min=10, max=300, step=5, mode="box"
        )
    )
    return vol.Schema(fields)


class SimpleHeatingManagerConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Simple Heating Manager."""

    VERSION = 2

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return SimpleHeatingManagerOptionsFlow(config_entry)

    def _has_global_entry(self) -> bool:
        for entry in self._async_current_entries():
            if entry.data.get(CONF_ENTRY_TYPE) == ENTRY_TYPE_GLOBAL:
                return True
        return False

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        if self._has_global_entry():
            return await self.async_step_add_room(user_input)
        return await self.async_step_global(user_input)

    async def async_step_global(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        if user_input is not None:
            return self.async_create_entry(
                title="Simple Heating Manager",
                data={**user_input, CONF_ENTRY_TYPE: ENTRY_TYPE_GLOBAL},
            )

        schema = vol.Schema(
            {
                vol.Required(CONF_CV_SWITCH_1): selector.EntitySelector(
                    selector.EntitySelectorConfig(
                        domain=["switch", "input_boolean"]
                    )
                ),
                vol.Optional(CONF_CV_SWITCH_2): selector.EntitySelector(
                    selector.EntitySelectorConfig(
                        domain=["switch", "input_boolean"]
                    )
                ),
                vol.Optional(
                    CONF_NOTIFICATION_SERVICE,
                    default=DEFAULT_NOTIFICATION_SERVICE,
                ): selector.TextSelector(),
            }
        )

        return self.async_show_form(step_id="user", data_schema=schema)

    async def async_step_add_room(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            for entry in self._async_current_entries():
                if entry.data.get(CONF_ROOM_NAME) == user_input[CONF_ROOM_NAME]:
                    errors["base"] = "room_already_exists"
                    break

            if not errors:
                return self.async_create_entry(
                    title=user_input[CONF_ROOM_NAME],
                    data={**user_input, CONF_ENTRY_TYPE: ENTRY_TYPE_ROOM},
                )

        return self.async_show_form(
            step_id="add_room",
            data_schema=_room_schema(),
            errors=errors,
        )

    async def async_step_add_room_internal(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Create a room entry (called from options flow)."""
        if user_input is not None:
            return self.async_create_entry(
                title=user_input[CONF_ROOM_NAME],
                data=user_input,
            )
        return self.async_abort(reason="unknown")


class SimpleHeatingManagerOptionsFlow(OptionsFlow):
    """Handle options flow — settings for global or room entries."""

    def __init__(self, config_entry: ConfigEntry) -> None:
        self._config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        if self._config_entry.data.get(CONF_ENTRY_TYPE) == ENTRY_TYPE_GLOBAL:
            return self.async_show_menu(
                step_id="init",
                menu_options=["settings", "add_room"],
            )
        return await self.async_step_edit_room(user_input)

    async def async_step_settings(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        if user_input is not None:
            new_data = {
                **user_input,
                CONF_ENTRY_TYPE: ENTRY_TYPE_GLOBAL,
            }
            self.hass.config_entries.async_update_entry(
                self._config_entry, data=new_data
            )
            return self.async_create_entry(title="", data={})

        current = self._config_entry.data

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_CV_SWITCH_1,
                    default=current.get(CONF_CV_SWITCH_1),
                ): selector.EntitySelector(
                    selector.EntitySelectorConfig(
                        domain=["switch", "input_boolean"]
                    )
                ),
                vol.Optional(
                    CONF_CV_SWITCH_2,
                    description={
                        "suggested_value": current.get(CONF_CV_SWITCH_2)
                    },
                ): selector.EntitySelector(
                    selector.EntitySelectorConfig(
                        domain=["switch", "input_boolean"]
                    )
                ),
                vol.Optional(
                    CONF_NOTIFICATION_SERVICE,
                    default=current.get(
                        CONF_NOTIFICATION_SERVICE,
                        DEFAULT_NOTIFICATION_SERVICE,
                    ),
                ): selector.TextSelector(),
            }
        )

        return self.async_show_form(step_id="settings", data_schema=schema)

    async def async_step_add_room(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            for entry in self.hass.config_entries.async_entries(DOMAIN):
                if entry.data.get(CONF_ROOM_NAME) == user_input[CONF_ROOM_NAME]:
                    errors["base"] = "room_already_exists"
                    break

            if not errors:
                await self.hass.config_entries.flow.async_init(
                    DOMAIN,
                    context={"source": "add_room_internal"},
                    data={**user_input, CONF_ENTRY_TYPE: ENTRY_TYPE_ROOM},
                )
                return self.async_create_entry(title="", data={})

        return self.async_show_form(
            step_id="add_room",
            data_schema=_room_schema(),
            errors=errors,
        )

    async def async_step_edit_room(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        errors: dict[str, str] = {}
        current = self._config_entry.data

        if user_input is not None:
            new_name = user_input[CONF_ROOM_NAME]
            for entry in self.hass.config_entries.async_entries(DOMAIN):
                if (
                    entry.entry_id != self._config_entry.entry_id
                    and entry.data.get(CONF_ROOM_NAME) == new_name
                ):
                    errors["base"] = "room_already_exists"
                    break

            if not errors:
                new_data = {
                    **user_input,
                    CONF_ENTRY_TYPE: ENTRY_TYPE_ROOM,
                }
                self.hass.config_entries.async_update_entry(
                    self._config_entry,
                    title=new_name,
                    data=new_data,
                )
                return self.async_create_entry(title="", data={})

        return self.async_show_form(
            step_id="edit_room",
            data_schema=_room_schema(dict(current)),
            errors=errors,
        )
