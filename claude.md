# CLAUDE.md

This file gives Claude Code persistent context for this project. Read it first
on every session.

## Project: Tesla Solar Charger

A Home Assistant custom integration that dynamically controls Tesla charging
to consume excess solar production. It is a *controller* integration — it does
not talk to the Tesla directly. It reads power sensors from Home Assistant and
drives existing entities exposed by a separate ESPHome Tesla BLE proxy.

The behaviour mirrors a small, well-defined subset of ChargeHQ
(<https://chargehq.net/features>). Where a behaviour is described below,
ChargeHQ's documented behaviour is the source of truth — do not invent
variations.

## Hard constraints

- **Do not invent features.** If a requirement is not in this file or in the
  build prompt, ask before adding it. The user has explicitly excluded home
  battery priority, scheduled charging, multi-vehicle support, and three-phase
  charging from the MVP. Do not silently add them.
- **Do not hardcode entity IDs.** All upstream entity IDs (the ESPHome BLE
  proxy's amps number, charging switch, charging state sensor, the user's
  production and consumption sensors) are configured by the user via the
  config flow. None of them have predictable names.
- **Do not assume vehicle voltage.** Default to 230 V single-phase but make it
  a config option. Watts-per-amp = `voltage × amps` (single-phase only in MVP).
- **Treat the BLE link as unreliable.** Commands may fail. Sensors may go
  unavailable. The integration must keep working (idle, not crash) when the
  car is asleep, out of BLE range, or the proxy is offline.

## Upstream dependencies (read-only references)

- ESPHome Tesla BLE proxy by yoziru:
  <https://github.com/yoziru/esphome-tesla-ble>
  - It exposes (entity types, not literal IDs):
    - a `number` for charging amps (range 0–`charging_amps_max`, default 32)
    - a `number` for charging limit (battery %)
    - a `switch` for charging on/off
    - a text/sensor for IEC 61851 state, with values
      `Disconnected`, `Complete`, `Stopped`, `Starting`, `Charging`,
      `Calibrating`, `NoPower`, `Unknown`
    - a binary sensor for asleep/awake
    - other diagnostic entities (BLE signal, doors, user present, charge flap)
  - The proxy uses an "11-minute wake window" before letting the car sleep.
    Active states (charging / unlocked / user present) override this.
  - Commands have latency. Setting amps, then reading back, can take several
    seconds. Do not treat a not-yet-reflected change as a failure.

- ChargeHQ behaviour we mirror (from
  <https://chargehq.net/kb/solar-tracking-settings> and
  <https://chargehq.net/kb/reducing-contactor-wear>):
  - **Solar Only**: charging power tracks available solar. If excess drops
    below the minimum charging rate, charging stops. No grid imports.
  - **Solar + Grid**: charging power tracks available solar. If excess drops
    below the minimum, charging continues at the minimum rate, with the
    shortfall imported from the grid. Stops outside solar hours
    (production below `min_solar_generation`).
  - **Hysteresis to reduce contactor wear:**
    - 6 minutes below threshold before stopping a charge
    - 15 minutes after stopping before restarting
  - **Tesla single-phase minimum**: 5 A (~1.2 kW @ 230 V)
  - **Min Solar Generation** threshold (default 0.2 kW): below this,
    charging stops in either mode
  - **Solar Tracking Margin**: `charging_power = available_solar - margin`
    (margin in watts, can be negative to allow grid import)
  - **Consumption Excludes Charging**: a flag for setups where the consumption
    sensor does not see the EV charging draw (most installs *do* see it). When
    enabled, do **not** add the current charge draw back when computing excess.

## Definitions

- `production_w` — instantaneous solar generation in watts, from a configured
  sensor. The sensor's `unit_of_measurement` (W or kW) must be honoured;
  internally the integration always works in watts.
- `consumption_w` — instantaneous house consumption in watts, summed across
  one or more configured sensors.
- `current_charge_w` — `voltage × current_amps`. `current_amps` is the
  *commanded* amps (the value the integration last successfully wrote to the
  ESPHome amps number).
- `excess_w` — available power for EV charging:
  - If consumption sensor *includes* EV charging (default):
    `excess_w = production_w − (consumption_w − current_charge_w) − margin_w`
  - If `consumption_excludes_charging` is true:
    `excess_w = production_w − consumption_w − margin_w`
- `target_amps` — `floor(excess_w / voltage)`, clamped to
  `[min_amps, max_amps]`. Use whole-amp granularity; the Tesla rounds anyway.
- `plugged_in` — IEC 61851 state in `{Complete, Stopped, Starting, Charging,
  Calibrating}`. Anything else (`Disconnected`, `NoPower`, `Unknown`,
  unavailable) is *not plugged in*.

## State machine

Modes (user-selected via `select` entity):

- **Off** — integration takes no actions. Existing charge state is left alone.
- **Solar Only** — track excess; stop below minimum.
- **Solar + Grid** — track excess; floor at minimum while solar present.
- **Charge Now** — force max amps and switch on; ignore solar.

States the coordinator tracks internally:

- `DISABLED` — mode is Off, or master enable switch is off.
- `IDLE` — enabled, but car not plugged in.
- `TRACKING` — actively setting amps based on excess.
- `STOPPING` — excess fell below threshold; running 6-minute stop timer.
- `COOLDOWN` — charging stopped; running 15-minute restart lockout.
- `FORCED` — Charge Now mode active.

Transitions are driven by the coordinator on every poll cycle (default 30 s).
Timers are wall-clock; they survive across polls but reset on mode change or
plug events.

## Architecture

- A single `DataUpdateCoordinator` runs the control loop. It polls every
  `update_interval` seconds, reads the configured input sensors via
  `hass.states.get`, computes the next action, and issues service calls
  (`number.set_value`, `switch.turn_on`, `switch.turn_off`) on the upstream
  ESPHome entities.
- Commands are only sent when the desired value differs from the last
  commanded value (debounce by exact equality on amps, by state on switch).
  This avoids flooding the BLE link.
- The integration's own entities (mode `select`, settings `number`s,
  diagnostic `sensor`s, master `switch`) are all backed by the coordinator's
  data dict. They never talk to the upstream BLE proxy directly.
- All blocking work goes through `hass.async_add_executor_job` if needed.
  There should be very little blocking work — this is a pure control loop.

## File layout

```
custom_components/tesla_solar_charger/
├── __init__.py             # async_setup_entry, async_unload_entry
├── manifest.json           # domain, name, version, iot_class=local_polling,
│                           # config_flow=true, integration_type=service
├── config_flow.py          # UI setup; entity selectors for all upstream IDs
├── const.py                # DOMAIN, defaults, mode enum, state enum
├── coordinator.py          # control loop, state machine, hysteresis timers
├── select.py               # mode entity
├── number.py               # min/max amps, margin, charge limit override
├── switch.py               # master enable
├── sensor.py               # diagnostic sensors (target amps, excess, state)
├── strings.json            # config flow text + translation keys
└── translations/
    └── en.json
hacs.json                   # at repo root, for HACS readiness
README.md
```

## Conventions

- Python 3.13+ syntax, type hints everywhere, `from __future__ import
  annotations` at the top of every module.
- Use `homeassistant.helpers.update_coordinator.DataUpdateCoordinator`. Do not
  roll a custom polling loop.
- Use entity selectors in the config flow
  (`selector.EntitySelector(EntitySelectorConfig(...))`) — never free-text
  entity IDs.
- All user-facing strings live in `strings.json` and `translations/en.json`.
- Config and options flow validate that the chosen entities exist *and* have
  expected `unit_of_measurement` (W or kW) for the power sensors.
- Logger name: `_LOGGER = logging.getLogger(__name__)`. Default level INFO;
  the per-cycle decision can log at DEBUG.

## What "done" looks like

- `homeassistant --script check_config` passes.
- `hassfest` (the official integration validator) passes.
- The integration installs cleanly via HACS as a custom repository.
- A user with a working ESPHome Tesla BLE proxy and one production +
  one consumption sensor can configure the integration entirely from the UI
  with no YAML.
- Switching modes through the `select` entity changes behaviour within one
  poll cycle, except for the documented 6 / 15 minute hysteresis windows.
- Unplugging the car returns the state machine to `IDLE` and stops issuing
  commands.

## Things to ask the user about, not assume

- Whether to add an "Apply Now" button entity that bypasses the restart
  cooldown.
- Whether to expose the Tesla's charge-limit (battery %) number as a
  passthrough — the BLE proxy already exposes one, so duplicating it inside
  this integration may be unwanted.
- Adding three-phase support, home-battery awareness, multi-vehicle support,
  or scheduled charging — these are out of scope for the MVP.
