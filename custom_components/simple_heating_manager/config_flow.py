"""Config flow for Simple Heating Manager."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, OptionsFlow
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import selector

from .const import (
    CONF_CALIBRATION_MODE,
    CONF_CHECK_INTERVAL,
    CONF_CV_SWITCH,
    CONF_NAME,
    CONF_NOTIFICATION_SERVICE,
    CONF_TARGET_TEMP,
    CONF_TEMP_SENSOR,
    CONF_TRV_ENTITY,
    CONF_WINDOW_SENSORS,
    DEFAULT_CALIBRATION_MODE,
    DEFAULT_CHECK_INTERVAL,
    DEFAULT_NOTIFICATION_SERVICE,
    DEFAULT_TARGET_TEMP,
    DOMAIN,
)

CALIBRATION_OPTIONS = [
    selector.SelectOptionDict(value="target_temp", label="Target temperature"),
    selector.SelectOptionDict(value="offset", label="Offset"),
    selector.SelectOptionDict(value="none", label="None"),
]


class SimpleHeatingManagerConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Simple Heating Manager."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._user_input: dict[str, Any] = {}

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        """Get the options flow handler."""
        return SimpleHeatingManagerOptionsFlow(config_entry)

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle step 1: basic room configuration."""
        errors: dict[str, str] = {}

        if user_input is not None:
            # Check for duplicate room names
            await self.async_set_unique_id(user_input[CONF_NAME])
            self._abort_if_unique_id_configured()

            self._user_input = user_input
            return await self.async_step_options()

        schema = vol.Schema(
            {
                vol.Required(CONF_NAME): selector.TextSelector(),
                vol.Required(CONF_TRV_ENTITY): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="climate")
                ),
                vol.Required(CONF_TEMP_SENSOR): selector.EntitySelector(
                    selector.EntitySelectorConfig(
                        domain="sensor", device_class="temperature"
                    )
                ),
            }
        )

        return self.async_show_form(
            step_id="user", data_schema=schema, errors=errors
        )

    async def async_step_options(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle step 2: optional settings."""
        if user_input is not None:
            data = {**self._user_input, **user_input}
            return self.async_create_entry(
                title=self._user_input[CONF_NAME], data=data
            )

        schema = vol.Schema(
            {
                vol.Optional(CONF_WINDOW_SENSORS): selector.EntitySelector(
                    selector.EntitySelectorConfig(
                        domain="binary_sensor", multiple=True
                    )
                ),
                vol.Optional(CONF_CV_SWITCH): selector.EntitySelector(
                    selector.EntitySelectorConfig(
                        domain=["switch", "input_boolean"]
                    )
                ),
                vol.Optional(
                    CONF_CALIBRATION_MODE, default=DEFAULT_CALIBRATION_MODE
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=CALIBRATION_OPTIONS, mode="dropdown"
                    )
                ),
                vol.Optional(
                    CONF_TARGET_TEMP, default=DEFAULT_TARGET_TEMP
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=5, max=35, step=0.5, unit_of_measurement="°C"
                    )
                ),
                vol.Optional(
                    CONF_CHECK_INTERVAL, default=DEFAULT_CHECK_INTERVAL
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=10, max=300, step=5, mode="box"
                    )
                ),
                vol.Optional(
                    CONF_NOTIFICATION_SERVICE, default=DEFAULT_NOTIFICATION_SERVICE
                ): selector.TextSelector(),
            }
        )

        return self.async_show_form(step_id="options", data_schema=schema)


class SimpleHeatingManagerOptionsFlow(OptionsFlow):
    """Handle options flow for Simple Heating Manager."""

    def __init__(self, config_entry: ConfigEntry) -> None:
        """Initialize options flow."""
        self._config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the options form."""
        if user_input is not None:
            # Merge options back into data
            new_data = {**self._config_entry.data, **user_input}
            self.hass.config_entries.async_update_entry(
                self._config_entry, data=new_data
            )
            return self.async_create_entry(title="", data={})

        current = self._config_entry.data

        schema = vol.Schema(
            {
                vol.Optional(
                    CONF_WINDOW_SENSORS,
                    default=current.get(CONF_WINDOW_SENSORS, []),
                ): selector.EntitySelector(
                    selector.EntitySelectorConfig(
                        domain="binary_sensor", multiple=True
                    )
                ),
                vol.Optional(
                    CONF_CV_SWITCH,
                    description={"suggested_value": current.get(CONF_CV_SWITCH)},
                ): selector.EntitySelector(
                    selector.EntitySelectorConfig(
                        domain=["switch", "input_boolean"]
                    )
                ),
                vol.Optional(
                    CONF_CALIBRATION_MODE,
                    default=current.get(
                        CONF_CALIBRATION_MODE, DEFAULT_CALIBRATION_MODE
                    ),
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=CALIBRATION_OPTIONS, mode="dropdown"
                    )
                ),
                vol.Optional(
                    CONF_TARGET_TEMP,
                    default=current.get(CONF_TARGET_TEMP, DEFAULT_TARGET_TEMP),
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=5, max=35, step=0.5, unit_of_measurement="°C"
                    )
                ),
                vol.Optional(
                    CONF_CHECK_INTERVAL,
                    default=current.get(CONF_CHECK_INTERVAL, DEFAULT_CHECK_INTERVAL),
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=10, max=300, step=5, mode="box"
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

        return self.async_show_form(step_id="init", data_schema=schema)
