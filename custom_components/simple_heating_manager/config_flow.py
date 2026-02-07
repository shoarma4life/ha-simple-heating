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


class SimpleHeatingManagerConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Simple Heating Manager."""

    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        """Get the options flow handler."""
        return SimpleHeatingManagerOptionsFlow(config_entry)

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Step 1: Global settings — CV switches and notifications."""
        if user_input is not None:
            await self.async_set_unique_id(DOMAIN)
            self._abort_if_unique_id_configured()

            return self.async_create_entry(
                title="Simple Heating Manager",
                data={**user_input, CONF_ROOMS: []},
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
                    CONF_NOTIFICATION_SERVICE, default=DEFAULT_NOTIFICATION_SERVICE
                ): selector.TextSelector(),
            }
        )

        return self.async_show_form(step_id="user", data_schema=schema)


class SimpleHeatingManagerOptionsFlow(OptionsFlow):
    """Handle options flow — menu with settings and add room."""

    def __init__(self, config_entry: ConfigEntry) -> None:
        """Initialize options flow."""
        self._config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Show menu: edit settings or add a room."""
        if user_input is not None:
            next_step = user_input.get("next_action")
            if next_step == "settings":
                return await self.async_step_settings()
            if next_step == "add_room":
                return await self.async_step_add_room()

        schema = vol.Schema(
            {
                vol.Required("next_action"): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[
                            selector.SelectOptionDict(
                                value="settings", label="Edit settings"
                            ),
                            selector.SelectOptionDict(
                                value="add_room", label="Add a room"
                            ),
                        ],
                        mode="list",
                    )
                ),
            }
        )

        return self.async_show_form(step_id="init", data_schema=schema)

    async def async_step_settings(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Edit global settings."""
        if user_input is not None:
            new_data = {**self._config_entry.data, **user_input}
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
                    description={"suggested_value": current.get(CONF_CV_SWITCH_2)},
                ): selector.EntitySelector(
                    selector.EntitySelectorConfig(
                        domain=["switch", "input_boolean"]
                    )
                ),
                vol.Optional(
                    CONF_NOTIFICATION_SERVICE,
                    default=current.get(
                        CONF_NOTIFICATION_SERVICE, DEFAULT_NOTIFICATION_SERVICE
                    ),
                ): selector.TextSelector(),
            }
        )

        return self.async_show_form(step_id="settings", data_schema=schema)

    async def async_step_add_room(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Add a new room."""
        errors: dict[str, str] = {}

        if user_input is not None:
            rooms = list(self._config_entry.data.get(CONF_ROOMS, []))
            existing_names = [r[CONF_ROOM_NAME] for r in rooms]
            if user_input[CONF_ROOM_NAME] in existing_names:
                errors["base"] = "room_already_exists"
            else:
                rooms.append(user_input)
                new_data = {**self._config_entry.data, CONF_ROOMS: rooms}
                self.hass.config_entries.async_update_entry(
                    self._config_entry, data=new_data
                )
                return self.async_create_entry(title="", data={})

        schema = vol.Schema(
            {
                vol.Required(CONF_ROOM_NAME): selector.TextSelector(),
                vol.Required(CONF_TRV_ENTITY): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="climate")
                ),
                vol.Required(CONF_TEMP_SENSOR): selector.EntitySelector(
                    selector.EntitySelectorConfig(
                        domain="sensor", device_class="temperature"
                    )
                ),
                vol.Optional(CONF_WINDOW_SENSORS): selector.EntitySelector(
                    selector.EntitySelectorConfig(
                        domain="binary_sensor", multiple=True
                    )
                ),
                vol.Optional(
                    CONF_CHECK_INTERVAL, default=DEFAULT_CHECK_INTERVAL
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=10, max=300, step=5, mode="box"
                    )
                ),
            }
        )

        return self.async_show_form(
            step_id="add_room", data_schema=schema, errors=errors
        )
