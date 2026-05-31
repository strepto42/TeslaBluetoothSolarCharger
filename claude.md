# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project: Tesla Solar Charger

A Home Assistant custom integration that dynamically controls Tesla charging
to consume excess solar production. It is a *controller* integration — it does
not talk to the Tesla directly. It reads power sensors from Home Assistant and
drives existing entities exposed by a separate ESPHome Tesla BLE proxy.

The behaviour mirrors a small, well-defined subset of ChargeHQ
(<https://chargehq.net/features>). Where a behaviour is described below,
ChargeHQ's documented behaviour is the source of truth — do not invent
variations.

## Commands

```bash
# Install test dependencies
pip install -r requirements_test.txt

# Run all tests
pytest

# Run a single test file
pytest tests/test_coordinator.py -v

# Run a single test by name
pytest tests/test_coordinator.py::test_name -v

# Validate the integration (requires homeassistant installed)
python -m homeassistant --script check_config
```

There is no build step. The integration is loaded directly by Home Assistant.

## Workflow rules (hard, non-negotiable)

These rules govern *how* work is done in this repo. They override default behaviour.

1. **Test-Driven Development.** Always write a meaningful, failing test before
   implementing a feature or fix. The test must exercise the actual behaviour
   under change — not a tautology. Run it and confirm it fails for the right
   reason before writing implementation code.
2. **Four-step workflow. Stop and wait for user confirmation at each step.**
   - **a) Understand** — Restate the problem in your own words. Ask the user
     to clarify anything ambiguous before proceeding. Do not move on until
     the user confirms the understanding is correct.
   - **b) Propose** — Present a detailed outline of the work: files to
     change, approach, edge cases, test strategy. Wait for user feedback and
     approval.
   - **c) Tests** — Write the failing tests aligned with the proposed design.
     Run them to demonstrate they fail. Show the user the failure output.
     Wait for confirmation before implementing.
   - **d) Implement** — Make the code changes. Run the tests to confirm they
     now pass. Stop for review. Do not bundle additional changes or "while
     I'm here" cleanups into this step.
3. **Never push to GitHub without explicit user permission.** This is a hard
   rule with no exceptions. `git push` (and `gh pr create`, `gh pr merge`,
   force-pushes, etc.) require an explicit instruction from the user in the
   current conversation. Prior approval does not carry forward.
4. **Never modify a test to make code pass.** If a test fails, fix the
   production code or — if the test itself is genuinely wrong — stop and
   discuss it with the user before changing the test. The arrow always
   points from test → code, never the reverse.
5. **Version the change in the same PR; tag after merge.** Any
   user-visible fix or feature ships a `manifest.json` `version` bump
   **inside the same PR as the change** — never as a separate follow-up
   PR, so one release maps cleanly to one change and master is never
   left with un-released work.
   - **Before opening the PR**, check the current state so you pick the
     right next version: read `manifest.json`'s `version`, and run
     `git tag` + `gh release list`. Do not assume the next number is
     free — a prior session may have already used it.
   - Bump to the next `MAJOR.MINOR.PATCH` accordingly and include that
     commit in the PR.
   - **After the PR merges**, create the matching annotated tag
     (`vMAJOR.MINOR.PATCH`, e.g. `v0.2.0`) and a GitHub *release* (HACS
     needs a release, not just a tag, to surface the update). The user
     pushes the tag (`git push origin vX.Y.Z`); never push tags without
     explicit instruction.
6. **Always work on a branch; land changes via PR.** Never commit
   directly to `master`. Open a feature/fix branch for every change,
   no matter how small (CI fix, doc tweak, typo). When ready, push the
   branch and open a PR with `gh pr create`. The user reviews and
   authorizes the merge; do not self-merge without confirmation. This
   applies even to follow-up fixes
   after a CI failure — open a new branch and a new PR, do not push
   straight to `master`.

## Hard constraints

- **Do not invent features.** If a requirement is not in this file or in the
  build prompt, ask before adding it. The user has explicitly excluded
  scheduled charging, multi-vehicle support, and three-phase charging
  from the MVP. Do not silently add them. Home battery awareness *is*
  in scope — see "Battery awareness" below.
- **Do not hardcode entity IDs.** All upstream entity IDs (the ESPHome BLE
  proxy's amps number, charging switch, charging state sensor, the user's
  production and consumption sensors) are configured by the user via the
  config flow. None of them have predictable names.
- **Do not assume vehicle voltage.** Default to 230 V single-phase but make it
  a config option. Watts-per-amp = `voltage × amps` (single-phase only in MVP).
- **Treat the BLE link as unreliable.** Commands may fail. Sensors may go
  unavailable. The integration must keep working (idle, not crash) when the
  car is asleep, out of BLE range, or the proxy is offline.
- **No self-references or unnecessary documentation.** Do not reference Claude in commit messages.
  Do not create unnecessary markdown files when making changes.

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
  - **Battery awareness (optional)**: when a battery power and SoC sensor
    pair are configured, the integration mirrors ChargeHQ's
    home-battery-charge-priority-limit-configuration behaviour:
    *"Once the limit is reached, all excess solar will be used for EV
    charging."* Below the configured `battery_priority_charge_limit_pct`,
    the home battery has priority and excess is gated to zero (state
    machine drops the EV to STOPPING through normal hysteresis). At/above
    the limit, the existing excess formula runs unchanged.
    Two styles are exposed: **hard_cutoff** (the strict ChargeHQ
    behaviour) and **graduated** (a known-good local automation's curve
    that tapers EV deduction in 5 % SoC bands above the limit, gentler
    on contactor wear).
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
- `battery_power_w` — instantaneous home-battery power, normalised so
  positive = charging regardless of the user's sensor sign convention
  (the `battery_power_positive_is_charging` toggle). `None` if not
  configured or if either battery sensor is unavailable.
- `battery_soc_pct` — home-battery state of charge, percentage. `None`
  if not configured or if either battery sensor is unavailable.
- `battery_priority_active` — true when this cycle's `excess_w` was
  reduced (or zeroed) by battery-priority gating.

## State machine

Modes (user-selected via `select` entity):

- **Off** — disables solar tracking and turns the charging switch off
  (once, debounced — no repeat commands afterwards). Amps are not changed.
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

Transitions are driven by the coordinator on every poll cycle (default 5 s,
configurable via the **Update Interval** NumberEntity on the device's
dashboard). Timers are wall-clock; they survive across polls but reset on
mode change or plug events.

## Architecture

`TeslaSolarChargerCoordinator` in `coordinator.py` is the heart of the integration. On each poll (`_async_update_data`):

1. Read `production_w` and `consumption_w` from configured sensor entity IDs via `hass.states.get`. Production unavailable → treat as 0 W. Consumption unavailable → solar tracking disabled (Charge Now / Off still work).
2. Compute `excess_w` using `_compute_excess_w_with_values`. The formula accounts for whether the consumption sensor already includes the EV draw, and gates the EV-draw back-out on `_is_charging` — which is refreshed each cycle from the IEC `charging_state_sensor` (`_read_charging_active`), i.e. whether the car is *actually* drawing — so a stale `_commanded_amps` doesn't inflate household-load when the car isn't charging. Switch commands reconcile against this same observed state rather than trusting that the last BLE command landed (see step 6).
3. If a battery power+SoC sensor pair is configured and both are readable, apply `_apply_battery_priority(excess_w, soc_pct)` before the state machine sees `excess_w`. Below the limit → 0; at/above the limit → unchanged (hard cutoff) or bucketed deduction (graduated). Sensors unavailable → fall back to no-battery formula.
4. Advance the state machine (`_update_state_machine`): `DISABLED → IDLE → TRACKING → STOPPING → COOLDOWN → FORCED`. Hysteresis timers use `time.monotonic()` stored in `_stop_timer_start` / `_cooldown_timer_start`; they reset on plug events and mode changes.
5. Compute `target_amps = floor(excess_w / voltage)`, clamped to `[min_amps, max_amps]`.
6. Issue `number.set_value` / `switch.turn_on` / `switch.turn_off` service calls via `hass.services.async_call`. Amps are debounced against the last commanded value. The **switch is reconciled against the car's observed IEC state**, not our memory of the last command: while the car's reported charging state already matches intent we send nothing (flood protection); while it disagrees — e.g. a `turn_off` was dropped over the unreliable BLE link and the car is still `Charging` — we re-assert the command, throttled to no more than once per `SWITCH_RESEND_INTERVAL_SECONDS` for the same desired value (a genuine change sends immediately). This is what makes a dropped stop self-heal instead of stranding the car charging.
6. Return a `dict[str, Any]` snapshot; all platform entities (`select.py`, `number.py`, `switch.py`, `sensor.py`) read from this dict and never call services directly.

Config/options flow (`config_flow.py`) edits **entity bindings only**:
`production_sensor`, `consumption_sensors`, `consumption_excludes_charging`,
`amps_number`, `charging_switch`, `charging_state_sensor`, `voltage`,
`name`, plus the optional battery sensors and sign toggle. These are
saved to `entry.data`; the options flow preserves `entry.options`
verbatim on save (`OPTIONS_FIELDS` is empty by design).

Every runtime tunable lives on a dashboard control that writes directly
to `entry.options`:

- `number.py` — Min Amps, Max Amps, Margin (W), Update Interval (s),
  Minimum Solar Generation (W), Stop Delay (s), Restart Cooldown (s),
  Battery Priority Charge Limit (%; only when battery configured).
- `select.py` — Mode (always), Battery Priority Style (`hard_cutoff` /
  `graduated`; only when battery configured).

The Update Interval setter additionally mutates
`coordinator.update_interval` so changes take effect on the next cycle
without a reload. The coordinator reads tunables via `_get_config_value`,
which checks `entry.options` first then falls back to `entry.data` then
to a const default.

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
├── number.py               # min amps, max amps, margin (dashboard tunables)
├── switch.py               # master enable
├── sensor.py               # numeric/string diagnostic sensors
├── binary_sensor.py        # plugged_in, is_charging, last_command_succeeded
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

## Testing

Tests use `pytest-homeassistant-custom-component`. `pytest.ini` sets `asyncio_mode = auto` so async test functions run without `@pytest.mark.asyncio`.

`tests/conftest.py` provides two key fixtures:
- `mock_hass` — a `MagicMock(spec=HomeAssistant)` with `hass.services.async_call` as an `AsyncMock` and `hass.states.get` returning preconfigured sensor states.
- `mock_config_entry` — a `MagicMock(spec=ConfigEntry)` with realistic `entry.data` / `entry.options`.

Most coordinator tests instantiate `TeslaSolarChargerCoordinator(mock_hass, mock_config_entry)` directly and call `await coordinator._async_update_data()` to exercise the control loop without a running Home Assistant instance.

## Things to ask the user about, not assume

- Whether to add an "Apply Now" button entity that bypasses the restart
  cooldown.
- Whether to expose the Tesla's charge-limit (battery %) number as a
  passthrough — the BLE proxy already exposes one, so duplicating it inside
  this integration may be unwanted.
- Adding three-phase support, home-battery awareness, multi-vehicle support,
  or scheduled charging — these are out of scope for the MVP.
