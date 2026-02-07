"""Main loop and orchestration for Simple Heating Manager."""

import logging
import signal
import sys
import time

from .config import load_config
from .ha_api import HomeAssistantAPI
from .room import Room

_log = logging.getLogger("heating_manager")

_shutdown = False


def _handle_signal(signum, frame):
    global _shutdown
    _log.info("Received signal %s, shutting down...", signum)
    _shutdown = True


def _setup_logging(level_name: str) -> None:
    level = getattr(logging, level_name.upper(), logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        stream=sys.stdout,
    )


def _validate_entities(api: HomeAssistantAPI, rooms: list[Room]) -> None:
    """Validate that all configured entities exist in Home Assistant."""
    for room in rooms:
        cfg = room.config
        missing = []

        if not api.validate_entity(cfg.trv_entity):
            missing.append(cfg.trv_entity)
        if not api.validate_entity(cfg.temp_sensor):
            missing.append(cfg.temp_sensor)
        for sensor in cfg.window_sensors:
            if not api.validate_entity(sensor):
                missing.append(sensor)

        if missing:
            _log.warning(
                "Room '%s': the following entities were not found: %s",
                cfg.name,
                ", ".join(missing),
            )
        else:
            _log.info("Room '%s': all entities validated", cfg.name)


def main() -> None:
    config = load_config()
    _setup_logging(config.log_level)

    _log.info("Simple Heating Manager starting")
    _log.info(
        "Managing %d room(s), check interval: %ds",
        len(config.rooms),
        config.check_interval,
    )

    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)

    api = HomeAssistantAPI(notification_service=config.notification_service)

    rooms = [Room(room_config) for room_config in config.rooms]

    _log.info("Validating entities...")
    _validate_entities(api, rooms)

    _log.info("Entering main loop")
    while not _shutdown:
        for room in rooms:
            if _shutdown:
                break
            room.update(api)

        if not _shutdown:
            time.sleep(config.check_interval)

    _log.info("Simple Heating Manager stopped")


if __name__ == "__main__":
    main()
