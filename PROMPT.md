You are building a Home Assistant custom integration called
`tesla_solar_charger`. The full specification, conventions, and constraints
are in `CLAUDE.md` in the project root. Read it now and treat it as the
source of truth. Anything that contradicts `CLAUDE.md` is wrong.

The integration drives an existing ESPHome Tesla BLE proxy
(<https://github.com/yoziru/esphome-tesla-ble>) — it does not talk to the
Tesla directly. It mirrors a defined subset of ChargeHQ
(<https://chargehq.net/kb/solar-tracking-settings>,
<https://chargehq.net/kb/reducing-contactor-wear>).

Scope is fixed: single vehicle, single-phase, modes Off / Solar Only /
Solar + Grid / Charge Now, HACS-ready repo layout. Do not add features
outside this scope without asking.

## Build phases

Work through these phases in order. After each phase, stop and summarise
what you produced and what remains. Do not skip ahead.

### Phase 1 — Skeleton and manifest

Produce the file tree from `CLAUDE.md` with the following minimum content:

- `manifest.json` with: `domain: tesla_solar_charger`, `name: Tesla Solar
  Charger`, `version: 0.1.0`, `config_flow: true`, `integration_type:
  service`, `iot_class: local_polling`, `codeowners: ["@me"]`,
  `documentation` and `issue_tracker` pointing at
  `https://github.com/me/tesla_solar_charger` (placeholder),
  `requirements: []`.
- `hacs.json` at repo root with `name`, `homeassistant` minimum version
  (target current stable, look it up — do not guess), `render_readme: true`.
- `__init__.py` with `async_setup_entry` and `async_unload_entry` that load
  and unload the four platforms (`select`, `number`, `switch`, `sensor`).
  Set up the `DataUpdateCoordinator` here and store it on
  `entry.runtime_data`.
- `const.py` with the domain, default values, and Enums for `Mode` and
  `ControllerState`.
- Empty `strings.json` and `translations/en.json` with the top-level keys
  populated (config, options, entity).
- `README.md` with: what the integration does, prerequisites (working
  ESPHome Tesla BLE proxy, a production sensor in W or kW, at least one
  consumption sensor in W or kW), installation via HACS as a custom
  repository, and a screenshot placeholder.

Stop. Report file tree and confirm `hassfest`-style structure.

### Phase 2 — Config flow

Implement `config_flow.py` with a single user step that collects, in this
order:

1. `name` — display name for this config entry. Default: "Tesla Solar
   Charger".
2. `production_sensor` — `EntitySelector` filtered to `domain=sensor` and
   `device_class=power`.
3. `consumption_sensors` — `EntitySelector` with `multiple=true`, filtered
   to `domain=sensor` and `device_class=power`. At least one required.
4. `consumption_excludes_charging` — boolean. Default false. Help text
   should say: "Enable only if your consumption sensor does NOT include the
   EV charging circuit. Most installations do not need this."
5. `amps_number` — `EntitySelector` filtered to `domain=number`. The user
   picks the ESPHome BLE proxy's charging-amps number.
6. `charging_switch` — `EntitySelector` filtered to `domain=switch`.
7. `charging_state_sensor` — `EntitySelector` filtered to `domain=sensor`.
   This is the IEC 61851 text sensor from the BLE proxy. Used to determine
   plug-in state.
8. `voltage` — number, default 230, range 100–260.

Validate: the chosen power sensors must have `unit_of_measurement` of `W`
or `kW`; reject with an error key otherwise.

Implement an `OptionsFlow` exposing the same fields plus:

- `update_interval_seconds` (default 30, range 10–300)
- `min_amps` (default 5, range 1–32)
- `max_amps` (default 32, range 5–32)
- `margin_w` (default 0, range −5000 to 5000)
- `min_solar_generation_w` (default 200, range 0–10000)
- `stop_delay_seconds` (default 360 — 6 minutes)
- `restart_delay_seconds` (default 900 — 15 minutes)

Stop. Show me the config flow file and the schema before continuing.

### Phase 3 — Coordinator and control loop

Implement `coordinator.py`:

- Subclass `DataUpdateCoordinator[dict]`.
- `_async_update_data` reads all input sensors, computes the next action,
  applies the state machine, issues service calls, and returns a dict with:
  `mode`, `controller_state`, `production_w`, `consumption_w`, `excess_w`,
  `target_amps`, `commanded_amps`, `is_charging`, `plugged_in`,
  `seconds_until_next_transition`, `last_command_sent_at`,
  `last_command_succeeded`.
- Implement helpers:
  - `_read_power_w(entity_id) -> float | None` — reads state, converts kW
    to W, returns None on unavailable / unknown / parse error.
  - `_read_plug_state() -> bool` — maps the IEC 61851 sensor as defined in
    `CLAUDE.md`.
  - `_compute_excess_w()` — exactly the formula in `CLAUDE.md`.
  - `_send_amps(amps)` and `_send_switch(on: bool)` — call
    `hass.services.async_call` with `blocking=True`. Catch and log
    exceptions; set `last_command_succeeded` accordingly. Only send if the
    desired value differs from the last commanded value.

Implement the state machine exactly as described in `CLAUDE.md`. Use
`asyncio.Event`s or wall-clock timestamps stored on the coordinator for the
6-minute stop and 15-minute restart timers — not background tasks. The
timers are evaluated on each poll cycle.

Edge cases to handle explicitly:

- Production or consumption sensor is `unavailable` or `unknown`: hold
  current commanded amps, log at WARNING once per transition, do not change
  state.
- Plug state sensor is `unavailable`: assume not plugged in.
- A service call to set amps fails: do not update `commanded_amps`. Retry
  on the next cycle.
- Mode changes mid-cycle: cancel any running stop timer, but respect any
  active cooldown timer (the 15-minute lockout) unless mode is Charge Now.
- Charge Now bypasses both timers and sets amps to `max_amps`.

Stop. Walk me through the state machine implementation before continuing.

### Phase 4 — Platforms

Implement the four platforms. Each entity uses the coordinator's data and
inherits `CoordinatorEntity`.

`select.py`:

- One `SelectEntity`: options are `Off`, `Solar Only`, `Solar + Grid`,
  `Charge Now`. `async_select_option` updates the coordinator's mode and
  triggers an immediate refresh.

`number.py`:

- `min_amps`, `max_amps`, `margin_w` — these are settings, persisted in
  the config entry options. `async_set_native_value` updates options and
  refreshes.

`switch.py`:

- `master_enable` — when off, the integration acts as if mode is Off
  regardless of the select entity's value. Useful for "stop touching my car"
  without losing mode preference.

`sensor.py` — diagnostic sensors:

- `target_amps` (unit A, state class measurement)
- `commanded_amps` (unit A)
- `excess_solar` (unit W, device class power)
- `controller_state` (text)
- `seconds_until_next_transition` (unit s) — only meaningful in STOPPING or
  COOLDOWN states; otherwise 0.
- `last_command_succeeded` (binary-ish; expose as a sensor with on/off
  string for now, do not invent a binary_sensor platform unless asked).

Give every entity a stable `unique_id` of the form
`{config_entry_id}_{key}`, and a `DeviceInfo` so they group under one
device named "Tesla Solar Charger".

Stop. Show me one platform file fully and outline the others.

### Phase 5 — Validation, polish, README

- Run through the integration mentally and confirm every constraint in
  `CLAUDE.md` is satisfied. Output a checklist.
- Add brand directory placeholder (`brands/tesla_solar_charger/icon.png`
  is not required at this stage; a note in README is fine).
- Expand `README.md` to include: setup walkthrough, the four modes
  explained with one-paragraph each (lifted in spirit from ChargeHQ docs,
  but written in your own words — do not copy text), a worked example
  of the excess-solar formula, a troubleshooting section covering "car
  won't wake / amps not changing / sensor unavailable", and a "Known
  limitations" section that explicitly lists what is out of scope (home
  battery priority, three-phase, multi-vehicle, scheduling).
- Make sure logging is sane: one INFO line on mode change, one INFO line
  on charge start/stop, DEBUG for per-cycle decisions.
- Final check: search the codebase for hardcoded entity IDs, hardcoded
  voltages, and any feature outside the agreed scope. Remove or flag
  anything found.

Stop. Output the final file tree, a summary of what was built, and any
points where you had to make a judgment call.

## Rules of engagement

- If anything in `CLAUDE.md` or this prompt is ambiguous, **ask** — do not
  guess. The user has explicitly asked for no hallucinated requirements.
- Do not invent endpoints, entity IDs, or behaviour for the ESPHome Tesla
  BLE proxy. Treat its surface as: it exposes a number for amps, a switch
  for charging, a text sensor for IEC 61851 state, and other entities the
  user does not need for this MVP.
- Do not add tests or CI in this pass unless asked. Get the runtime
  correct first.
- Prefer reading from `CLAUDE.md` over re-deriving requirements from these
  instructions. They should agree; if they disagree, that is a bug —
  surface it.
