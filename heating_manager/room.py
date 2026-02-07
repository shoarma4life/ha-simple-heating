"""Room model and logic for Simple Heating Manager."""

import logging

from .config import RoomConfig
from .ha_api import HomeAssistantAPI

_log = logging.getLogger(__name__)


class Room:
    """Manages heating logic for a single room."""

    def __init__(self, config: RoomConfig):
        self.config = config
        self.window_open: bool = False
        self.previous_hvac_mode: str | None = None
        self.previous_temperature: float | None = None
        self.last_calibration_offset: float = 0.0

    def update(self, api: HomeAssistantAPI) -> None:
        """Main update cycle for this room."""
        try:
            windows_open = self._check_windows(api)

            if windows_open and not self.window_open:
                self._handle_window_opened(api)
            elif not windows_open and self.window_open:
                self._handle_window_closed(api)

            if not windows_open:
                self._calibrate(api)

        except Exception:
            _log.exception("Error updating room '%s'", self.config.name)

    def _check_windows(self, api: HomeAssistantAPI) -> bool:
        """Check if any window sensor reports open."""
        for sensor_id in self.config.window_sensors:
            try:
                state = api.get_state(sensor_id)
                if state.get("state") == "on":
                    _log.debug(
                        "Room '%s': window sensor %s is open",
                        self.config.name,
                        sensor_id,
                    )
                    return True
            except Exception:
                _log.exception(
                    "Room '%s': error reading window sensor %s",
                    self.config.name,
                    sensor_id,
                )
        return False

    def _handle_window_opened(self, api: HomeAssistantAPI) -> None:
        """Handle window opening: save state and turn off TRV."""
        _log.info(
            "Room '%s': window opened, turning off heating", self.config.name
        )

        try:
            trv_state = api.get_state(self.config.trv_entity)
            self.previous_hvac_mode = trv_state.get("state", "heat")
            attrs = trv_state.get("attributes", {})
            self.previous_temperature = attrs.get("temperature")
        except Exception:
            _log.exception(
                "Room '%s': error reading TRV state before turning off",
                self.config.name,
            )
            self.previous_hvac_mode = "heat"
            self.previous_temperature = None

        try:
            api.set_trv_hvac_mode(self.config.trv_entity, "off")
        except Exception:
            _log.exception(
                "Room '%s': error turning off TRV", self.config.name
            )

        self.window_open = True

        try:
            api.send_notification(
                title="Heating Manager",
                message=f"Room '{self.config.name}': window opened, heating turned off.",
            )
        except Exception:
            _log.exception(
                "Room '%s': error sending window open notification",
                self.config.name,
            )

    def _handle_window_closed(self, api: HomeAssistantAPI) -> None:
        """Handle window closing: restore previous TRV state."""
        _log.info(
            "Room '%s': window closed, restoring heating", self.config.name
        )

        try:
            if self.previous_hvac_mode and self.previous_hvac_mode != "off":
                api.set_trv_hvac_mode(
                    self.config.trv_entity, self.previous_hvac_mode
                )
            else:
                api.set_trv_hvac_mode(self.config.trv_entity, "heat")

            if self.previous_temperature is not None:
                api.set_trv_temperature(
                    self.config.trv_entity, self.previous_temperature
                )
        except Exception:
            _log.exception(
                "Room '%s': error restoring TRV state", self.config.name
            )

        self.window_open = False
        self.previous_hvac_mode = None
        self.previous_temperature = None

        try:
            api.send_notification(
                title="Heating Manager",
                message=f"Room '{self.config.name}': window closed, heating restored.",
            )
        except Exception:
            _log.exception(
                "Room '%s': error sending window close notification",
                self.config.name,
            )

    def _calibrate(self, api: HomeAssistantAPI) -> None:
        """Perform TRV calibration based on external temperature sensor."""
        if self.config.calibration_mode == "none":
            return

        try:
            external_state = api.get_state(self.config.temp_sensor)
            external_temp = float(external_state.get("state", 0))
        except (ValueError, TypeError):
            _log.warning(
                "Room '%s': could not read external temperature from %s",
                self.config.name,
                self.config.temp_sensor,
            )
            return
        except Exception:
            _log.exception(
                "Room '%s': error reading external sensor %s",
                self.config.name,
                self.config.temp_sensor,
            )
            return

        try:
            trv_state = api.get_state(self.config.trv_entity)
            attrs = trv_state.get("attributes", {})
            trv_internal_temp = attrs.get("current_temperature")
            if trv_internal_temp is None:
                _log.warning(
                    "Room '%s': TRV %s has no current_temperature attribute",
                    self.config.name,
                    self.config.trv_entity,
                )
                return
            trv_internal_temp = float(trv_internal_temp)
        except (ValueError, TypeError):
            _log.warning(
                "Room '%s': could not parse TRV internal temperature",
                self.config.name,
            )
            return
        except Exception:
            _log.exception(
                "Room '%s': error reading TRV state", self.config.name
            )
            return

        if self.config.calibration_mode == "offset":
            self._calibrate_offset(api, external_temp, trv_internal_temp)
        elif self.config.calibration_mode == "target_temp":
            self._calibrate_target_temp(api, external_temp, trv_internal_temp)

    def _calibrate_offset(
        self,
        api: HomeAssistantAPI,
        external_temp: float,
        trv_internal_temp: float,
    ) -> None:
        """Calibrate using offset mode.

        Calculates the difference between external and TRV internal temperature
        and sets it as the calibration offset on the TRV's offset entity.
        """
        offset = round(external_temp - trv_internal_temp, 1)

        if offset == self.last_calibration_offset:
            _log.debug(
                "Room '%s': offset unchanged (%.1f), skipping",
                self.config.name,
                offset,
            )
            return

        # Derive the offset entity from the TRV entity name
        # e.g., climate.living_room_trv -> number.living_room_trv_local_temperature_calibration
        trv_name = self.config.trv_entity.split(".", 1)[1]
        offset_entity = f"number.{trv_name}_local_temperature_calibration"

        _log.info(
            "Room '%s': setting offset to %.1f (external=%.1f, trv=%.1f)",
            self.config.name,
            offset,
            external_temp,
            trv_internal_temp,
        )

        try:
            api.set_trv_offset(offset_entity, offset)
            self.last_calibration_offset = offset
        except Exception:
            _log.exception(
                "Room '%s': error setting calibration offset on %s",
                self.config.name,
                offset_entity,
            )

    def _calibrate_target_temp(
        self,
        api: HomeAssistantAPI,
        external_temp: float,
        trv_internal_temp: float,
    ) -> None:
        """Calibrate using target temperature mode.

        Adjusts the TRV target temperature to compensate for the difference
        between external and TRV internal temperature readings.

        Example: desired 21C, external reads 19C, TRV reads 21C
        -> delta = 19 - 21 = -2
        -> adjusted_target = 21 - (-2) = 23C (TRV heats more)
        """
        if self.config.target_temperature is None:
            return

        delta = external_temp - trv_internal_temp
        adjusted_target = round(self.config.target_temperature - delta, 1)

        _log.info(
            "Room '%s': target_temp calibration: desired=%.1f, "
            "external=%.1f, trv_internal=%.1f, delta=%.1f, adjusted=%.1f",
            self.config.name,
            self.config.target_temperature,
            external_temp,
            trv_internal_temp,
            delta,
            adjusted_target,
        )

        try:
            api.set_trv_temperature(self.config.trv_entity, adjusted_target)
        except Exception:
            _log.exception(
                "Room '%s': error setting adjusted target temperature",
                self.config.name,
            )
