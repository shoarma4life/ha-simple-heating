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
    CONF_CV_SWITCH,
    CONF_NAME,
    CONF_NOTIFICATION_SERVICE,
    CONF_TEMP_SENSOR,
    CONF_TRV_ENTITY,
    CONF_WINDOW_SENSORS,
    DEFAULT_CHECK_INTERVAL,
    DEFAULT_NOTIFICATION_SERVICE,
    DOMAIN,
)


def _get_existing_cv_switch(hass) -> str | None:
    """Get CV switch from an already configured room (if any)."""
    for entry in hass.config_entries.async_entries(DOMAIN):
        cv = entry.data.get(CONF_CV_SWITCH)
        if cv:
            return cv
    return None


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
        """Handle step 1: CV switch + room basics."""
        errors: dict[str, str] = {}

        if user_input is not None:
            await self.async_set_unique_id(user_input[CONF_NAME])
            self._abort_if_unique_id_configured()

            self._user_input = user_input
            return await self.async_step_options()

        # Pre-fill CV switch from existing rooms
        existing_cv = _get_existing_cv_switch(self.hass)

        schema_dict: dict[Any, Any] = {}

        if existing_cv:
            schema_dict[vol.Optional(CONF_CV_SWITCH, description={
                "suggested_value": existing_cv
            })] = selector.EntitySelector(
                selector.EntitySelectorConfig(
                    domain=["switch", "input_boolean"]
                )
            )
        else:
            schema_dict[vol.Optional(CONF_CV_SWITCH)] = selector.EntitySelector(
                selector.EntitySelectorConfig(
                    domain=["switch", "input_boolean"]
                )
            )

        schema_dict[vol.Required(CONF_NAME)] = selector.TextSelector()
        schema_dict[vol.Required(CONF_TRV_ENTITY)] = selector.EntitySelector(
            selector.EntitySelectorConfig(domain="climate")
        )
        schema_dict[vol.Required(CONF_TEMP_SENSOR)] = selector.EntitySelector(
            selector.EntitySelectorConfig(
                domain="sensor", device_class="temperature"
            )
        )

        return self.async_show_form(
            step_id="user", data_schema=vol.Schema(schema_dict), errors=errors
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
            new_data = {**self._config_entry.data, **user_input}
            self.hass.config_entries.async_update_entry(
                self._config_entry, data=new_data
            )
            return self.async_create_entry(title="", data={})

        current = self._config_entry.data

        schema = vol.Schema(
            {
                vol.Optional(
                    CONF_CV_SWITCH,
                    description={"suggested_value": current.get(CONF_CV_SWITCH)},
                ): selector.EntitySelector(
                    selector.EntitySelectorConfig(
                        domain=["switch", "input_boolean"]
                    )
                ),
                vol.Optional(
                    CONF_WINDOW_SENSORS,
                    default=current.get(CONF_WINDOW_SENSORS, []),
                ): selector.EntitySelector(
                    selector.EntitySelectorConfig(
                        domain="binary_sensor", multiple=True
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
