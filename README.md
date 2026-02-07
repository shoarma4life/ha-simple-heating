# Simple Heating Manager

A Home Assistant custom integration (HACS) that manages heating per room using TRV calibration via external temperature sensors and automatic window detection.

## Features

- **TRV Calibration**: Compensate for inaccurate TRV temperature readings using an external sensor
  - **Offset mode**: Sets the TRV's calibration offset entity (for Zigbee TRVs with offset support)
  - **Target temperature mode**: Adjusts the target temperature to compensate (works with any TRV)
- **Window Detection**: Automatically turns off heating when a window is opened and restores it when closed
- **Notifications**: Sends alerts when heating state changes due to window events
- **Entity Pickers**: Select your TRV, temperature sensor, and window sensors from a list (no more manual typing)
- **Brand-independent**: Works with any climate entity in Home Assistant
- **Works everywhere**: Runs on any Home Assistant installation (not just HA OS/Supervised)

## Installation

### HACS (recommended)

1. Open HACS in your Home Assistant instance
2. Go to **Integrations** and click the three-dot menu
3. Select **Custom repositories**
4. Add this repository URL and select **Integration** as the category
5. Click **Add**, then find "Simple Heating Manager" and install it
6. Restart Home Assistant

### Manual

1. Copy the `custom_components/simple_heating_manager` folder to your Home Assistant `config/custom_components/` directory
2. Restart Home Assistant

## Configuration

1. Go to **Settings** > **Devices & Services** > **Add Integration**
2. Search for "Simple Heating Manager"
3. Follow the setup wizard:
   - **Step 1**: Enter a room name, select your TRV (climate entity) and external temperature sensor
   - **Step 2**: Optionally add window sensors, choose a calibration mode, set desired temperature and check interval
4. Repeat for each room you want to manage

### Options

After setup you can change options by clicking **Configure** on the integration entry.

| Option | Description | Default |
|--------|-------------|---------|
| Window sensors | Binary sensors that detect open windows | _(none)_ |
| Calibration mode | `target_temp`, `offset`, or `none` | `target_temp` |
| Desired temperature | Target room temperature (for target_temp mode) | `21.0 °C` |
| Check interval | How often to check and calibrate (seconds) | `30` |
| Boiler switch | Switch/input_boolean that controls the boiler | _(none)_ |
| Notification service | Service for notifications | `persistent_notification.create` |

### Boiler switch

Each room can optionally reference a switch (or input_boolean) that controls the central heating boiler. The switch is turned **on** when any room needs heat, and only turned **off** when **no room** using that switch needs heat anymore. This prevents the boiler from turning off while other rooms are still heating.

### Calibration modes

- **Target temperature**: Adjusts the TRV's target temperature to compensate for the difference between the external sensor and the TRV's internal reading. Works with any TRV.
- **Offset**: Calculates `offset = external_temp - trv_internal_temp` and writes it to the TRV's `local_temperature_calibration` number entity. Best for Zigbee TRVs with offset support.
- **None**: No calibration, only window detection.

## Repository

This project is maintained in two locations:

- **Source**: https://git.voskuil.cloud/marco/ha-simple-heating
- **GitHub mirror (for HACS)**: https://github.com/shoarma4life/ha-simple-heating
