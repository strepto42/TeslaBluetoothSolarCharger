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
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import (
    AMPS_MAX_LIMIT,
    AMPS_MIN_LIMIT,
    DEFAULT_MARGIN_W,
    DEFAULT_MAX_AMPS,
    DEFAULT_MIN_AMPS,
    DEFAULT_MIN_SOLAR_GENERATION_W,
    DEFAULT_NAME,
    DEFAULT_RESTART_DELAY_SECONDS,
    DEFAULT_STOP_DELAY_SECONDS,
    DEFAULT_UPDATE_INTERVAL_SECONDS,
    DEFAULT_VOLTAGE,
    DOMAIN,
    MARGIN_MAX,
    MARGIN_MIN,
    MIN_SOLAR_GENERATION_MAX,
    MIN_SOLAR_GENERATION_MIN,
    UPDATE_INTERVAL_MAX,
    UPDATE_INTERVAL_MIN,
    VOLTAGE_MAX,
    VOLTAGE_MIN,
)

_LOGGER = logging.getLogger(__name__)

# Valid power units
VALID_POWER_UNITS = {UnitOfPower.WATT, UnitOfPower.KILO_WATT, "W", "kW"}


def _get_user_schema(defaults: dict[str, Any] | None = None) -> vol.Schema:
    """Get the schema for the user step."""
    defaults = defaults or {}
    return vol.Schema(
        {
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
    )


def _get_options_schema(defaults: dict[str, Any]) -> vol.Schema:
    """Get the schema for the options flow."""
    return vol.Schema(
        {
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
                "min_amps",
                default=defaults.get("min_amps", DEFAULT_MIN_AMPS),
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=AMPS_MIN_LIMIT,
                    max=AMPS_MAX_LIMIT,
                    step=1,
                    unit_of_measurement="A",
                    mode=selector.NumberSelectorMode.BOX,
                )
            ),
            vol.Required(
                "max_amps",
                default=defaults.get("max_amps", DEFAULT_MAX_AMPS),
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=AMPS_MIN_LIMIT,
                    max=AMPS_MAX_LIMIT,
                    step=1,
                    unit_of_measurement="A",
                    mode=selector.NumberSelectorMode.BOX,
                )
            ),
            vol.Required(
                "margin_w",
                default=defaults.get("margin_w", DEFAULT_MARGIN_W),
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=MARGIN_MIN,
                    max=MARGIN_MAX,
                    step=1,
                    unit_of_measurement="W",
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
    )


class TeslaSolarChargerConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Tesla Solar Charger."""

    VERSION = 1

    def _validate_power_sensor(self, entity_id: str) -> bool:
        """Validate that a sensor has a valid power unit."""
        state = self.hass.states.get(entity_id)
        if state is None:
            return False
        unit = state.attributes.get("unit_of_measurement")
        return unit in VALID_POWER_UNITS

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            # Validate production sensor unit
            if not self._validate_power_sensor(user_input["production_sensor"]):
                errors["production_sensor"] = "invalid_power_unit"

            # Validate consumption sensors
            consumption_sensors = user_input.get("consumption_sensors", [])
            if not consumption_sensors:
                errors["consumption_sensors"] = "no_consumption_sensors"
            else:
                for sensor_id in consumption_sensors:
                    if not self._validate_power_sensor(sensor_id):
                        errors["consumption_sensors"] = "invalid_power_unit"
                        break

            if not errors:
                # Store config data in entry.data
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
        return TeslaSolarChargerOptionsFlow(config_entry)


class TeslaSolarChargerOptionsFlow(OptionsFlow):
    """Handle options flow for Tesla Solar Charger."""

    def __init__(self, config_entry: ConfigEntry) -> None:
        """Initialize options flow."""
        self.config_entry = config_entry

    def _validate_power_sensor(self, entity_id: str) -> bool:
        """Validate that a sensor has a valid power unit."""
        state = self.hass.states.get(entity_id)
        if state is None:
            return False
        unit = state.attributes.get("unit_of_measurement")
        return unit in VALID_POWER_UNITS

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle options flow."""
        errors: dict[str, str] = {}

        if user_input is not None:
            # Validate production sensor unit
            if not self._validate_power_sensor(user_input["production_sensor"]):
                errors["production_sensor"] = "invalid_power_unit"

            # Validate consumption sensors
            consumption_sensors = user_input.get("consumption_sensors", [])
            if not consumption_sensors:
                errors["consumption_sensors"] = "no_consumption_sensors"
            else:
                for sensor_id in consumption_sensors:
                    if not self._validate_power_sensor(sensor_id):
                        errors["consumption_sensors"] = "invalid_power_unit"
                        break

            if not errors:
                # Update both data and options
                self.hass.config_entries.async_update_entry(
                    self.config_entry,
                    data=user_input,
                    title=user_input.get("name", DEFAULT_NAME),
                )
                return self.async_create_entry(title="", data={})

        # Merge current data with options for defaults
        defaults = {**self.config_entry.data, **self.config_entry.options}

        return self.async_show_form(
            step_id="init",
            data_schema=_get_options_schema(defaults),
            errors=errors,
        )

