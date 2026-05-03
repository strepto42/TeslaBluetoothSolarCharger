"""Config flow for Tesla Solar Charger."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import UnitOfPower
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import selector

from .const import (
    DEFAULT_MIN_SOLAR_GENERATION_W,
    DEFAULT_NAME,
    DEFAULT_RESTART_DELAY_SECONDS,
    DEFAULT_STOP_DELAY_SECONDS,
    DEFAULT_UPDATE_INTERVAL_SECONDS,
    DEFAULT_VOLTAGE,
    DOMAIN,
    MIN_SOLAR_GENERATION_MAX,
    MIN_SOLAR_GENERATION_MIN,
    UPDATE_INTERVAL_MAX,
    UPDATE_INTERVAL_MIN,
    VOLTAGE_MAX,
    VOLTAGE_MIN,
)

_LOGGER = logging.getLogger(__name__)

# Valid power units accepted by the production/consumption sensor validators.
VALID_POWER_UNITS = {UnitOfPower.WATT, UnitOfPower.KILO_WATT, "W", "kW"}

# Fields that bind to upstream entities or hardware identity. These are stored
# in entry.data and survive across options-flow saves.
DATA_FIELDS: frozenset[str] = frozenset(
    {
        "name",
        "production_sensor",
        "consumption_sensors",
        "consumption_excludes_charging",
        "amps_number",
        "charging_switch",
        "charging_state_sensor",
        "voltage",
    }
)

# Fields that are user-tunable runtime parameters. Stored in entry.options.
# min_amps/max_amps/margin_w are NOT here — they are owned by the dashboard
# NumberEntity widgets, which write them directly to entry.options.
OPTIONS_FIELDS: frozenset[str] = frozenset(
    {
        "update_interval_seconds",
        "min_solar_generation_w",
        "stop_delay_seconds",
        "restart_delay_seconds",
    }
)


def _validate_power_sensor(hass: HomeAssistant, entity_id: str) -> bool:
    """Return True if `entity_id` exists and reports a watts/kilowatts unit."""
    state = hass.states.get(entity_id)
    if state is None:
        return False
    return state.attributes.get("unit_of_measurement") in VALID_POWER_UNITS


def _validate_user_input(
    hass: HomeAssistant, user_input: dict[str, Any]
) -> dict[str, str]:
    """Validate sensor units and required fields. Returns a field→error map."""
    errors: dict[str, str] = {}

    if not _validate_power_sensor(hass, user_input["production_sensor"]):
        errors["production_sensor"] = "invalid_power_unit"

    consumption_sensors = user_input.get("consumption_sensors", [])
    if not consumption_sensors:
        errors["consumption_sensors"] = "no_consumption_sensors"
    else:
        for sensor_id in consumption_sensors:
            if not _validate_power_sensor(hass, sensor_id):
                errors["consumption_sensors"] = "invalid_power_unit"
                break

    return errors


def _bindings_schema(defaults: dict[str, Any]) -> dict[Any, Any]:
    """Schema fragment for the entity-binding fields (kept in entry.data)."""
    return {
        vol.Required(
            "name", default=defaults.get("name", DEFAULT_NAME)
        ): selector.TextSelector(),
        vol.Required(
            "production_sensor",
            default=defaults.get("production_sensor"),
        ): selector.EntitySelector(
            selector.EntitySelectorConfig(
                domain="sensor",
                device_class="power",
            )
        ),
        vol.Required(
            "consumption_sensors",
            default=defaults.get("consumption_sensors", []),
        ): selector.EntitySelector(
            selector.EntitySelectorConfig(
                domain="sensor",
                device_class="power",
                multiple=True,
            )
        ),
        vol.Required(
            "consumption_excludes_charging",
            default=defaults.get("consumption_excludes_charging", False),
        ): selector.BooleanSelector(),
        vol.Required(
            "amps_number",
            default=defaults.get("amps_number"),
        ): selector.EntitySelector(
            selector.EntitySelectorConfig(domain="number")
        ),
        vol.Required(
            "charging_switch",
            default=defaults.get("charging_switch"),
        ): selector.EntitySelector(
            selector.EntitySelectorConfig(domain="switch")
        ),
        vol.Required(
            "charging_state_sensor",
            default=defaults.get("charging_state_sensor"),
        ): selector.EntitySelector(
            selector.EntitySelectorConfig(domain="sensor")
        ),
        vol.Required(
            "voltage",
            default=defaults.get("voltage", DEFAULT_VOLTAGE),
        ): selector.NumberSelector(
            selector.NumberSelectorConfig(
                min=VOLTAGE_MIN,
                max=VOLTAGE_MAX,
                step=1,
                unit_of_measurement="V",
                mode=selector.NumberSelectorMode.BOX,
            )
        ),
    }


def _timing_schema(defaults: dict[str, Any]) -> dict[Any, Any]:
    """Schema fragment for the timing/threshold fields (kept in entry.options)."""
    return {
        vol.Required(
            "update_interval_seconds",
            default=defaults.get(
                "update_interval_seconds", DEFAULT_UPDATE_INTERVAL_SECONDS
            ),
        ): selector.NumberSelector(
            selector.NumberSelectorConfig(
                min=UPDATE_INTERVAL_MIN,
                max=UPDATE_INTERVAL_MAX,
                step=1,
                unit_of_measurement="s",
                mode=selector.NumberSelectorMode.BOX,
            )
        ),
        vol.Required(
            "min_solar_generation_w",
            default=defaults.get(
                "min_solar_generation_w", DEFAULT_MIN_SOLAR_GENERATION_W
            ),
        ): selector.NumberSelector(
            selector.NumberSelectorConfig(
                min=MIN_SOLAR_GENERATION_MIN,
                max=MIN_SOLAR_GENERATION_MAX,
                step=1,
                unit_of_measurement="W",
                mode=selector.NumberSelectorMode.BOX,
            )
        ),
        vol.Required(
            "stop_delay_seconds",
            default=defaults.get("stop_delay_seconds", DEFAULT_STOP_DELAY_SECONDS),
        ): selector.NumberSelector(
            selector.NumberSelectorConfig(
                min=0,
                max=3600,
                step=1,
                unit_of_measurement="s",
                mode=selector.NumberSelectorMode.BOX,
            )
        ),
        vol.Required(
            "restart_delay_seconds",
            default=defaults.get(
                "restart_delay_seconds", DEFAULT_RESTART_DELAY_SECONDS
            ),
        ): selector.NumberSelector(
            selector.NumberSelectorConfig(
                min=0,
                max=7200,
                step=1,
                unit_of_measurement="s",
                mode=selector.NumberSelectorMode.BOX,
            )
        ),
    }


def _get_user_schema(defaults: dict[str, Any] | None = None) -> vol.Schema:
    """Schema for the initial config flow — bindings only."""
    return vol.Schema(_bindings_schema(defaults or {}))


def _get_options_schema(defaults: dict[str, Any]) -> vol.Schema:
    """Schema for the options flow — bindings + timing."""
    return vol.Schema({**_bindings_schema(defaults), **_timing_schema(defaults)})


class TeslaSolarChargerConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Tesla Solar Charger."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            errors = _validate_user_input(self.hass, user_input)
            if not errors:
                return self.async_create_entry(
                    title=user_input.get("name", DEFAULT_NAME),
                    data=user_input,
                )

        return self.async_show_form(
            step_id="user",
            data_schema=_get_user_schema(user_input),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        """Get the options flow for this handler."""
        return TeslaSolarChargerOptionsFlow()


class TeslaSolarChargerOptionsFlow(OptionsFlow):
    """Handle options flow for Tesla Solar Charger."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle options flow."""
        errors: dict[str, str] = {}

        if user_input is not None:
            errors = _validate_user_input(self.hass, user_input)

            if not errors:
                # Split user_input by destination. Bindings → data, tunables →
                # options. Preserve any existing options keys we don't manage
                # (e.g. min_amps/max_amps/margin_w written by NumberEntity).
                new_data = {
                    k: v for k, v in user_input.items() if k in DATA_FIELDS
                }
                new_options = {
                    **self.config_entry.options,
                    **{k: v for k, v in user_input.items() if k in OPTIONS_FIELDS},
                }
                self.hass.config_entries.async_update_entry(
                    self.config_entry,
                    data=new_data,
                    options=new_options,
                    title=user_input.get("name", DEFAULT_NAME),
                )
                return self.async_create_entry(title="", data={})

        # Merge current data with options for form defaults
        defaults = {**self.config_entry.data, **self.config_entry.options}

        return self.async_show_form(
            step_id="init",
            data_schema=_get_options_schema(defaults),
            errors=errors,
        )
