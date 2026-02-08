"""Constants for Simple Heating Manager."""

DOMAIN = "simple_heating_manager"

# Entry type marker
CONF_ENTRY_TYPE = "entry_type"
ENTRY_TYPE_GLOBAL = "global"
ENTRY_TYPE_ROOM = "room"

# Global settings
CONF_CV_SWITCH_1 = "cv_switch_1"
CONF_CV_SWITCH_2 = "cv_switch_2"
CONF_NOTIFICATION_SERVICE = "notification_service"

# Room settings
CONF_ROOM_NAME = "name"
CONF_TRV_ENTITY = "trv_entity"
CONF_TEMP_SENSOR = "temp_sensor"
CONF_WINDOW_SENSORS = "window_sensors"
CONF_SENSOR_MODE_ENTITY = "sensor_mode_entity"
CONF_ROOM_SWITCH = "room_switch"
CONF_CHECK_INTERVAL = "check_interval"

# Legacy (single-entry with rooms list)
CONF_ROOMS = "rooms"

DEFAULT_CHECK_INTERVAL = 30
DEFAULT_NOTIFICATION_SERVICE = "persistent_notification.create"
