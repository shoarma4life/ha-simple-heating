# Simple Heating Manager

A Home Assistant custom integration (HACS) that manages heating per room. The TRV decides when to heat — SHM just makes sure it has the right temperature reading, controls the boiler, and handles window detection.

## What it does

1. **Push external temperature to TRV** — Reads an external temperature sensor and writes the offset to the TRV's `local_temperature_calibration` entity, so the TRV knows the real room temperature and can decide itself when to heat.
2. **Boiler switch** — Turns on a switch (e.g. your CV boiler relay) when the TRV is heating. Only turns it off when no room sharing that switch needs heat anymore.
3. **Window detection** — Turns off the TRV when a window opens, restores the previous state when it closes.

## Installation

### HACS (recommended)

1. Open HACS in your Home Assistant instance
2. Go to **Integrations** and click the three-dot menu
3. Select **Custom repositories**
4. Add `https://github.com/shoarma4life/ha-simple-heating` and select **Integration** as the category
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
   - **Step 2**: Optionally add window sensors, boiler switch, check interval, and notification service
4. Repeat for each room you want to manage

### Options

After setup you can change options by clicking **Configure** on the integration entry.

| Option | Description | Default |
|--------|-------------|---------|
| Window sensors | Binary sensors that detect open windows | _(none)_ |
| Boiler switch | Switch/input_boolean that controls the boiler | _(none)_ |
| Check interval | How often to check and update (seconds) | `30` |
| Notification service | Service for notifications | `persistent_notification.create` |

## Repository

This project is maintained in two locations:

- **Source**: https://git.voskuil.cloud/marco/ha-simple-heating
- **GitHub mirror (for HACS)**: https://github.com/shoarma4life/ha-simple-heating
