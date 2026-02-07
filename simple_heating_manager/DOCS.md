# Simple Heating Manager - Documentation

## Configuration

Configure the add-on through the Home Assistant add-on options panel.

### Room Configuration

Each room requires:

| Option | Type | Required | Description |
|--------|------|----------|-------------|
| `name` | string | Yes | Friendly name for the room |
| `trv_entity` | string | Yes | Climate entity ID of the TRV |
| `temp_sensor` | string | Yes | External temperature sensor entity ID |
| `window_sensors` | list | No | Binary sensor entity IDs for window contacts |
| `calibration_mode` | string | No | `offset`, `target_temp`, or `none` (default: `none`) |
| `target_temperature` | float | No | Desired temperature (required for `target_temp` mode) |

### Global Options

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `check_interval` | int | 30 | Seconds between update cycles |
| `notification_service` | string | `persistent_notification.create` | HA notification service |
| `log_level` | string | `info` | Logging level: `debug`, `info`, `warning`, `error` |

### Example Configuration

```yaml
rooms:
  - name: "Living Room"
    trv_entity: "climate.living_room_trv"
    temp_sensor: "sensor.living_room_temperature"
    window_sensors:
      - "binary_sensor.living_room_window"
      - "binary_sensor.living_room_door"
    calibration_mode: "target_temp"
    target_temperature: 21.0
  - name: "Bedroom"
    trv_entity: "climate.bedroom_trv"
    temp_sensor: "sensor.bedroom_temperature"
    window_sensors:
      - "binary_sensor.bedroom_window"
    calibration_mode: "offset"
  - name: "Kitchen"
    trv_entity: "climate.kitchen_trv"
    temp_sensor: "sensor.kitchen_temperature"
    calibration_mode: "none"
check_interval: 30
notification_service: "persistent_notification.create"
log_level: "info"
```

## Calibration Modes

### Offset Mode

For TRVs that expose a calibration offset entity (common with Zigbee TRVs like Sonoff TRVZB, Moes, etc.).

The add-on automatically derives the offset entity name from the TRV entity:
- `climate.living_room_trv` -> `number.living_room_trv_local_temperature_calibration`

**How it works:**
1. Reads the external sensor temperature
2. Reads the TRV's internal temperature (from `current_temperature` attribute)
3. Calculates: `offset = external_temp - trv_internal_temp`
4. Sets the offset on the TRV's calibration entity

### Target Temperature Mode

Works with any TRV. Adjusts the target temperature to compensate for temperature reading differences.

**How it works:**
1. Reads the external sensor temperature
2. Reads the TRV's internal temperature
3. Calculates: `adjusted_target = desired_target - (external_temp - trv_internal_temp)`
4. Sets the adjusted target on the TRV

**Example:** Desired 21C, external reads 19C, TRV reads 21C:
- Delta = 19 - 21 = -2
- Adjusted target = 21 - (-2) = 23C
- The TRV will heat more to compensate

## Window Detection

When a window sensor reports `on` (open):
1. The current TRV HVAC mode and temperature are saved
2. The TRV is set to `off`
3. A notification is sent

When all windows close again:
1. The previous HVAC mode is restored
2. The previous target temperature is restored
3. A notification is sent

Multiple window sensors per room are supported. If **any** window is open, heating is turned off.

## Troubleshooting

- Set `log_level` to `debug` for verbose logging
- Check the add-on logs in the Home Assistant Supervisor panel
- Ensure all entity IDs are correct and the entities exist
- The add-on validates entities on startup and logs warnings for missing ones
