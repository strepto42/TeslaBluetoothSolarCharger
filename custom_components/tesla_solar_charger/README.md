# Tesla Solar Charger

A Home Assistant custom integration that automatically adjusts your Tesla's charging rate based on excess solar production, using an ESPHome Tesla BLE proxy for vehicle communication.

## What It Does

This integration monitors your solar production and home consumption, calculates the excess power available, and automatically adjusts your Tesla's charging amperage to make optimal use of your solar energy. It communicates with your Tesla via a local ESPHome-based Bluetooth LE proxy, requiring no cloud connectivity.

**Core formula:**
```
excess_power = solar_production - home_consumption
target_charge_amps = excess_power / voltage
```

## Prerequisites

Before installing this integration, you need:

1. **Working ESPHome Tesla BLE Proxy** - An ESP32 device running [esphome-tesla-ble](https://github.com/yoziru/esphome-tesla-ble), paired with your Tesla and integrated into Home Assistant.

2. **Solar Production Sensor** - A sensor entity in Home Assistant measuring your solar production in **W** (watts) or **kW** (kilowatts). This typically comes from your solar inverter integration.

3. **Home Consumption Sensor(s)** - One or more sensor entities measuring your home's power consumption in **W** or **kW**. This typically comes from your energy monitor or smart meter integration.

## Installation

### Via HACS (Recommended)

1. Open HACS in Home Assistant
2. Click the three dots menu in the top right
3. Select "Custom repositories"
4. Add this repository URL: `https://github.com/me/tesla_solar_charger`
5. Select category: "Integration"
6. Click "Add"
7. Find "Tesla Solar Charger" in HACS and install it
8. Restart Home Assistant

### Manual Installation

1. Copy the `custom_components/tesla_solar_charger` folder to your Home Assistant `config/custom_components/` directory
2. Restart Home Assistant

## Configuration

1. Go to **Settings** → **Devices & Services** → **Add Integration**
2. Search for "Tesla Solar Charger"
3. Follow the setup wizard to configure:
   - Solar production sensor
   - Home consumption sensor(s)
   - ESPHome BLE proxy entities (amps number, charging switch, state sensor)
   - Grid voltage

## Screenshot

*Screenshot placeholder - add screenshot of configuration flow here*

## Modes

The integration supports four charging modes:

- **Off** - Charging control is disabled
- **Solar Only** - Only charge when excess solar is available
- **Solar + Grid** - Use solar when available, supplement with grid power
- **Charge Now** - Charge at maximum rate immediately

## Support

For issues and feature requests, please use the [GitHub issue tracker](https://github.com/me/tesla_solar_charger/issues).

## License

This project is licensed under the MIT License.

