# Tesla Solar Charger

A Home Assistant custom integration that automatically adjusts your Tesla's charging rate based on excess solar production, using an ESPHome Tesla BLE proxy for vehicle communication.

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)

## What It Does

This integration monitors your solar production and home consumption, calculates the excess power available, and automatically adjusts your Tesla's charging amperage to make optimal use of your solar energy. It communicates with your Tesla via a local ESPHome-based Bluetooth LE proxy, requiring no cloud connectivity.

The behavior mirrors a subset of [ChargeHQ](https://chargehq.net/features) — specifically solar tracking with hysteresis to reduce contactor wear.

## Prerequisites

Before installing this integration, you need:

1. **Working ESPHome Tesla BLE Proxy** - An ESP32 device running [esphome-tesla-ble](https://github.com/yoziru/esphome-tesla-ble), paired with your Tesla and integrated into Home Assistant. This proxy exposes:
   - A `number` entity for charging amps
   - A `switch` entity for charging on/off
   - A `sensor` entity for IEC 61851 charging state

2. **Solar Production Sensor** - A sensor entity in Home Assistant measuring your solar production in **W** (watts) or **kW** (kilowatts). This typically comes from your solar inverter integration.

3. **Home Consumption Sensor(s)** - One or more sensor entities measuring your home's power consumption in **W** or **kW**. This typically comes from your energy monitor or smart meter integration.

## Installation

### Via HACS (Recommended)

1. Open HACS in Home Assistant
2. Click the three dots menu in the top right
3. Select "Custom repositories"
4. Add this repository URL: `https://github.com/strepto42/TeslaBluetoothSolarCharger`
5. Select category: "Integration"
6. Click "Add"
7. Find "Tesla Solar Charger" in HACS and install it
8. Restart Home Assistant

### Manual Installation

1. Copy the `custom_components/tesla_solar_charger` folder to your Home Assistant `config/custom_components/` directory
2. Restart Home Assistant

## Configuration

### Initial Setup

1. Go to **Settings** → **Devices & Services** → **Add Integration**
2. Search for "Tesla Solar Charger"
3. Configure the required entities:
   - **Solar Production Sensor**: Your solar inverter's power output sensor
   - **Home Consumption Sensor(s)**: Your energy monitor's consumption sensor(s)
   - **Charging Amps Number**: The ESPHome BLE proxy's amps number entity
   - **Charging Switch**: The ESPHome BLE proxy's charging switch entity
   - **Charging State Sensor**: The ESPHome BLE proxy's IEC 61851 state sensor
   - **Grid Voltage**: Your local grid voltage (typically 230V EU, 120V US)

4. Optionally configure `Consumption excludes EV charging` - only enable this if your consumption sensor does NOT include the EV charging circuit (most installations do NOT need this).

### Options

After setup, you can configure additional options:

| Option | Default | Description |
|--------|---------|-------------|
| Update Interval | 30s | How often to recalculate and adjust (10-300s) |
| Min Amps | 5A | Minimum charging amperage (Tesla minimum is 5A) |
| Max Amps | 32A | Maximum charging amperage |
| Margin | 0W | Buffer to subtract from excess (-5000 to 5000W) |
| Min Solar Generation | 200W | Solar threshold below which charging stops |
| Stop Delay | 360s | Wait time before stopping charge (6 minutes) |
| Restart Delay | 900s | Cooldown after stopping before restart (15 minutes) |

## Modes

### Off
The integration takes no actions. Any existing charge session is left alone. Use this when you want manual control of your Tesla's charging.

### Solar Only
Charging power tracks available excess solar. The integration calculates how much solar power is being exported (or would be exported) and sets the charging amperage to consume that excess. If excess drops below the minimum charging rate (5A × voltage), charging stops after a 6-minute delay. Charging will not restart for 15 minutes to reduce contactor wear. This mode never imports from the grid for charging.

### Solar + Grid
Charging power tracks available excess solar, but if excess drops below the minimum charging rate, charging continues at the minimum rate with the shortfall imported from the grid. Charging only stops when solar production falls below the `Min Solar Generation` threshold (default 200W). This allows you to maintain a charge session during brief cloud cover while still prioritizing solar.

### Charge Now
Immediately starts charging at maximum configured amperage, ignoring all solar calculations. This mode bypasses all timers and restrictions. Use this when you need to charge regardless of solar availability.

## How Excess Solar is Calculated

The integration uses this formula:

```
excess_w = production_w - (consumption_w - current_charge_w) - margin_w
target_amps = floor(excess_w / voltage)
```

### Worked Example

**Setup:**
- Solar production: 5000W
- Home consumption (including EV): 3500W
- Currently charging at: 10A @ 230V = 2300W
- Margin: 100W

**Calculation:**
```
current_charge_w = 10A × 230V = 2300W
base_consumption = 3500W - 2300W = 1200W  (home use without EV)
excess_w = 5000W - 1200W - 100W = 3700W
target_amps = floor(3700W / 230V) = 16A
```

The integration would set charging to 16A.

**If consumption sensor excludes EV charging** (consumption_excludes_charging = true):
```
excess_w = 5000W - 1200W - 100W = 3700W  (same result, different path)
```

## Entities Created

The integration creates these entities:

### Controls
- **Mode** (select): Off / Solar Only / Solar + Grid / Charge Now
- **Master Enable** (switch): Global enable/disable
- **Minimum Amps** (number): Min charging amperage
- **Maximum Amps** (number): Max charging amperage  
- **Margin** (number): Watts buffer for excess calculation

### Sensors
- **Target Amps**: Calculated target amperage
- **Commanded Amps**: Last amperage sent to car
- **Excess Solar**: Calculated excess watts
- **Controller State**: Current state machine state
- **Plugged In**: Whether car is detected as plugged in
- **Is Charging**: Whether we've commanded charging on
- **Solar Production**: Current production reading
- **Home Consumption**: Current consumption reading
- **Diagnostics**: Summary with all data as attributes

## Troubleshooting

### Car won't wake / commands not working

1. **Check BLE proxy status**: Ensure your ESPHome Tesla BLE proxy is online and connected
2. **Check car is in range**: BLE has limited range (~10m). The proxy must be near the car.
3. **Verify entity IDs**: In the Diagnostics sensor attributes, check `config_amps_number` and `config_charging_switch` match your actual ESPHome entities
4. **Check Home Assistant logs**: Look for error messages from `tesla_solar_charger`

### Amps not changing

1. **Check Controller State**: If state is `disabled`, `idle`, or `cooldown`, charging won't be adjusted
2. **Verify Plugged In**: The "Plugged In" sensor must show "yes"
3. **Check excess calculation**: Look at "Excess Solar" sensor - if negative, there's no excess to use
4. **Check Last Command Succeeded**: If "off", commands are failing (check logs)

### Sensor unavailable warnings

- **Production unavailable**: Treated as 0W. This is normal at night when solar inverters go offline.
- **Consumption unavailable**: Solar tracking is disabled, but "Charge Now" and "Off" modes still work.

### Charging stops unexpectedly

1. **Check stop delay**: Charging won't stop immediately when excess drops - it waits 6 minutes
2. **Check cooldown**: After stopping, charging won't restart for 15 minutes
3. **Check Controller State**: `stopping` = waiting to stop, `cooldown` = waiting to restart

### Integration not responding to mode changes

1. Ensure **Master Enable** switch is on
2. Check the **Diagnostics** sensor for current state
3. Look at Home Assistant logs for any errors

## Known Limitations

This integration is intentionally limited in scope for the MVP:

- **Single vehicle only** - Multi-vehicle support is not implemented
- **Single-phase only** - Three-phase charging calculations are not supported
- **No home battery awareness** - Does not account for home battery charge/discharge
- **No scheduled charging** - No time-based charging schedules
- **No Tesla cloud** - Requires local ESPHome BLE proxy; does not use Tesla's API

These may be added in future versions based on user feedback.

## Technical Details

- Uses Home Assistant's `DataUpdateCoordinator` for polling
- Default poll interval: 30 seconds
- Communicates with Tesla via ESPHome BLE proxy service calls
- No cloud dependencies - fully local operation
- All entity IDs are user-configured, never hardcoded

## Support

For issues and feature requests, please use the [GitHub issue tracker](https://github.com/strepto42/TeslaBluetoothSolarCharger/issues).

## License

This project is licensed under the MIT License.

---

*Note: This integration does not include a custom icon. It uses Home Assistant's default integration icon.*
