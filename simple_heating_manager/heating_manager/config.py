"""Configuration parsing for Simple Heating Manager."""

import json
import logging
from dataclasses import dataclass, field

OPTIONS_PATH = "/data/options.json"

_log = logging.getLogger(__name__)


@dataclass
class RoomConfig:
    name: str
    trv_entity: str
    temp_sensor: str
    window_sensors: list[str] = field(default_factory=list)
    calibration_mode: str = "none"
    target_temperature: float | None = None


@dataclass
class AppConfig:
    rooms: list[RoomConfig] = field(default_factory=list)
    check_interval: int = 30
    notification_service: str = "persistent_notification.create"
    log_level: str = "info"


def load_config(path: str = OPTIONS_PATH) -> AppConfig:
    """Load and validate configuration from options.json."""
    _log.info("Loading configuration from %s", path)

    with open(path, "r") as f:
        raw = json.load(f)

    rooms = []
    for room_data in raw.get("rooms", []):
        name = room_data.get("name", "")
        trv_entity = room_data.get("trv_entity", "")
        temp_sensor = room_data.get("temp_sensor", "")

        if not name or not trv_entity or not temp_sensor:
            _log.warning(
                "Skipping room with missing required fields: %s", room_data
            )
            continue

        window_sensors = room_data.get("window_sensors", [])
        calibration_mode = room_data.get("calibration_mode", "target_temp")
        target_temperature = room_data.get("target_temperature")

        if calibration_mode not in ("offset", "target_temp", "none"):
            _log.warning(
                "Room '%s': invalid calibration_mode '%s', defaulting to 'target_temp'",
                name,
                calibration_mode,
            )
            calibration_mode = "target_temp"

        if calibration_mode == "target_temp" and target_temperature is None:
            _log.info(
                "Room '%s': no target_temperature set, defaulting to 21.0",
                name,
            )
            target_temperature = 21.0

        rooms.append(
            RoomConfig(
                name=name,
                trv_entity=trv_entity,
                temp_sensor=temp_sensor,
                window_sensors=window_sensors,
                calibration_mode=calibration_mode,
                target_temperature=target_temperature,
            )
        )

    config = AppConfig(
        rooms=rooms,
        check_interval=raw.get("check_interval", 30),
        notification_service=raw.get(
            "notification_service", "persistent_notification.create"
        ),
        log_level=raw.get("log_level", "info"),
    )

    _log.info(
        "Configuration loaded: %d room(s), check_interval=%ds",
        len(config.rooms),
        config.check_interval,
    )

    return config
