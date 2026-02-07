"""Constants for Simple Heating Manager."""

DOMAIN = "simple_heating_manager"

CONF_NAME = "name"
CONF_TRV_ENTITY = "trv_entity"
CONF_TEMP_SENSOR = "temp_sensor"
CONF_WINDOW_SENSORS = "window_sensors"
CONF_CALIBRATION_MODE = "calibration_mode"
CONF_TARGET_TEMP = "target_temperature"
CONF_CHECK_INTERVAL = "check_interval"
CONF_NOTIFICATION_SERVICE = "notification_service"
CONF_CV_SWITCH = "cv_switch"

DEFAULT_CALIBRATION_MODE = "target_temp"
DEFAULT_TARGET_TEMP = 21.0
DEFAULT_CHECK_INTERVAL = 30
DEFAULT_NOTIFICATION_SERVICE = "persistent_notification.create"
