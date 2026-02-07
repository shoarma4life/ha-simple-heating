# Simple Heating Manager

A Home Assistant add-on that manages heating per room using TRV calibration via external temperature sensors and automatic window detection.

## Features

- **TRV Calibration**: Compensate for inaccurate TRV temperature readings using an external sensor
  - **Offset mode**: Sets the TRV's calibration offset entity (for Zigbee TRVs with offset support)
  - **Target temperature mode**: Adjusts the target temperature to compensate (works with any TRV)
- **Window Detection**: Automatically turns off heating when a window is opened and restores it when closed
- **Notifications**: Sends alerts when heating state changes due to window events
- **Brand-independent**: Works with any climate entity in Home Assistant

## Installation

1. Add this repository to your Home Assistant add-on store
2. Install the "Simple Heating Manager" add-on
3. Configure your rooms in the add-on options
4. Start the add-on

## Configuration

See [DOCS.md](DOCS.md) for detailed configuration instructions.
