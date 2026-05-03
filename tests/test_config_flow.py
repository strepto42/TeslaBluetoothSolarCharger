"""Tests for config_flow.py - Phase 2."""
from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfPower
from homeassistant.core import HomeAssistant, State
from homeassistant.data_entry_flow import FlowResultType

from custom_components.tesla_solar_charger.const import (
    DEFAULT_NAME,
    DEFAULT_VOLTAGE,
    DOMAIN,
)
from custom_components.tesla_solar_charger.config_flow import (
    TeslaSolarChargerConfigFlow,
    TeslaSolarChargerOptionsFlow,
    VALID_POWER_UNITS,
)


class TestValidPowerUnits:
    """Test valid power unit constants."""

    def test_watt_accepted(self):
        """Test W is accepted."""
        assert "W" in VALID_POWER_UNITS
        assert UnitOfPower.WATT in VALID_POWER_UNITS

    def test_kilowatt_accepted(self):
        """Test kW is accepted."""
        assert "kW" in VALID_POWER_UNITS
        assert UnitOfPower.KILO_WATT in VALID_POWER_UNITS


class TestConfigFlow:
    """Test config flow."""

    @pytest.fixture
    def flow(self, mock_hass: MagicMock) -> TeslaSolarChargerConfigFlow:
        """Create a config flow instance."""
        flow = TeslaSolarChargerConfigFlow()
        flow.hass = mock_hass
        return flow

    @pytest.mark.asyncio
    async def test_user_step_shows_form(self, flow: TeslaSolarChargerConfigFlow):
        """Test user step shows form when no input."""
        result = await flow.async_step_user(user_input=None)

        assert result["type"] == FlowResultType.FORM
        assert result["step_id"] == "user"
        assert result["errors"] == {}

    @pytest.mark.asyncio
    async def test_user_step_creates_entry_with_valid_input(
        self, flow: TeslaSolarChargerConfigFlow
    ):
        """Test user step creates entry with valid input."""
        user_input = {
            "name": "My Tesla Charger",
            "production_sensor": "sensor.solar_production",
            "consumption_sensors": ["sensor.home_consumption"],
            "consumption_excludes_charging": False,
            "amps_number": "number.tesla_charging_amps",
            "charging_switch": "switch.tesla_charging",
            "charging_state_sensor": "sensor.tesla_charging_state",
            "voltage": 230,
        }

        result = await flow.async_step_user(user_input=user_input)

        assert result["type"] == FlowResultType.CREATE_ENTRY
        assert result["title"] == "My Tesla Charger"
        assert result["data"] == user_input

    @pytest.mark.asyncio
    async def test_user_step_validates_production_sensor_unit(
        self, flow: TeslaSolarChargerConfigFlow, mock_hass: MagicMock
    ):
        """Test validation rejects sensors without W or kW unit."""
        # Set up invalid sensor (no power unit)
        mock_hass.states.get = MagicMock(return_value=State(
            "sensor.invalid", "100", {"unit_of_measurement": "°C"}
        ))

        user_input = {
            "name": "Tesla",
            "production_sensor": "sensor.invalid",
            "consumption_sensors": ["sensor.home_consumption"],
            "consumption_excludes_charging": False,
            "amps_number": "number.tesla_charging_amps",
            "charging_switch": "switch.tesla_charging",
            "charging_state_sensor": "sensor.tesla_charging_state",
            "voltage": 230,
        }

        result = await flow.async_step_user(user_input=user_input)

        assert result["type"] == FlowResultType.FORM
        assert "production_sensor" in result["errors"]
        assert result["errors"]["production_sensor"] == "invalid_power_unit"

    @pytest.mark.asyncio
    async def test_user_step_requires_consumption_sensors(
        self, flow: TeslaSolarChargerConfigFlow
    ):
        """Test validation requires at least one consumption sensor."""
        user_input = {
            "name": "Tesla",
            "production_sensor": "sensor.solar_production",
            "consumption_sensors": [],  # Empty list
            "consumption_excludes_charging": False,
            "amps_number": "number.tesla_charging_amps",
            "charging_switch": "switch.tesla_charging",
            "charging_state_sensor": "sensor.tesla_charging_state",
            "voltage": 230,
        }

        result = await flow.async_step_user(user_input=user_input)

        assert result["type"] == FlowResultType.FORM
        assert "consumption_sensors" in result["errors"]
        assert result["errors"]["consumption_sensors"] == "no_consumption_sensors"

    @pytest.mark.asyncio
    async def test_user_step_validates_consumption_sensor_units(
        self, flow: TeslaSolarChargerConfigFlow, mock_hass: MagicMock
    ):
        """Test validation checks all consumption sensor units."""
        def get_state(entity_id: str):
            if entity_id == "sensor.solar_production":
                return State(entity_id, "3000", {"unit_of_measurement": "W"})
            elif entity_id == "sensor.invalid_consumption":
                return State(entity_id, "100", {"unit_of_measurement": "°C"})
            return None

        mock_hass.states.get = MagicMock(side_effect=get_state)

        user_input = {
            "name": "Tesla",
            "production_sensor": "sensor.solar_production",
            "consumption_sensors": ["sensor.invalid_consumption"],
            "consumption_excludes_charging": False,
            "amps_number": "number.tesla_charging_amps",
            "charging_switch": "switch.tesla_charging",
            "charging_state_sensor": "sensor.tesla_charging_state",
            "voltage": 230,
        }

        result = await flow.async_step_user(user_input=user_input)

        assert result["type"] == FlowResultType.FORM
        assert "consumption_sensors" in result["errors"]
        assert result["errors"]["consumption_sensors"] == "invalid_power_unit"

    @pytest.mark.asyncio
    async def test_user_step_accepts_kw_unit(
        self, flow: TeslaSolarChargerConfigFlow, mock_hass: MagicMock
    ):
        """Test validation accepts kW unit."""
        def get_state(entity_id: str):
            return State(entity_id, "3.5", {"unit_of_measurement": "kW"})

        mock_hass.states.get = MagicMock(side_effect=get_state)

        user_input = {
            "name": "Tesla",
            "production_sensor": "sensor.solar_production",
            "consumption_sensors": ["sensor.home_consumption"],
            "consumption_excludes_charging": False,
            "amps_number": "number.tesla_charging_amps",
            "charging_switch": "switch.tesla_charging",
            "charging_state_sensor": "sensor.tesla_charging_state",
            "voltage": 230,
        }

        result = await flow.async_step_user(user_input=user_input)

        assert result["type"] == FlowResultType.CREATE_ENTRY

    @pytest.mark.asyncio
    async def test_user_step_default_name(
        self, flow: TeslaSolarChargerConfigFlow
    ):
        """Test default name is used when not specified."""
        user_input = {
            "name": DEFAULT_NAME,
            "production_sensor": "sensor.solar_production",
            "consumption_sensors": ["sensor.home_consumption"],
            "consumption_excludes_charging": False,
            "amps_number": "number.tesla_charging_amps",
            "charging_switch": "switch.tesla_charging",
            "charging_state_sensor": "sensor.tesla_charging_state",
            "voltage": DEFAULT_VOLTAGE,
        }

        result = await flow.async_step_user(user_input=user_input)

        assert result["type"] == FlowResultType.CREATE_ENTRY
        assert result["title"] == DEFAULT_NAME


class TestOptionsFlow:
    """Test options flow."""

    @pytest.fixture
    def options_flow(
        self, mock_hass: MagicMock, mock_config_entry: ConfigEntry
    ) -> TeslaSolarChargerOptionsFlow:
        """Create an options flow instance.

        Modern HA's OptionsFlow takes no constructor args; the `config_entry`
        property looks up `hass.config_entries.async_get_known_entry(handler)`,
        where `handler` is set to the entry_id by the framework. We replicate
        that wiring on the mock.
        """
        flow = TeslaSolarChargerOptionsFlow()
        flow.hass = mock_hass
        flow.handler = mock_config_entry.entry_id
        mock_hass.config_entries.async_get_known_entry = MagicMock(
            return_value=mock_config_entry
        )
        return flow

    @pytest.mark.asyncio
    async def test_init_step_shows_form(
        self, options_flow: TeslaSolarChargerOptionsFlow
    ):
        """Test init step shows form with current values."""
        result = await options_flow.async_step_init(user_input=None)

        assert result["type"] == FlowResultType.FORM
        assert result["step_id"] == "init"

    @pytest.mark.asyncio
    async def test_options_includes_timing_settings(
        self, options_flow: TeslaSolarChargerOptionsFlow
    ):
        """Test options flow includes timing settings not in initial config."""
        # These settings should be available in options but not initial config
        user_input = {
            "name": "Tesla Solar Charger",
            "production_sensor": "sensor.solar_production",
            "consumption_sensors": ["sensor.home_consumption"],
            "consumption_excludes_charging": False,
            "amps_number": "number.tesla_charging_amps",
            "charging_switch": "switch.tesla_charging",
            "charging_state_sensor": "sensor.tesla_charging_state",
            "voltage": 230,
            "update_interval_seconds": 60,  # Changed from default 30
            "min_amps": 6,  # Changed from default 5
            "max_amps": 16,  # Changed from default 32
            "margin_w": 100,  # Changed from default 0
            "min_solar_generation_w": 300,  # Changed from default 200
            "stop_delay_seconds": 480,  # Changed from default 360
            "restart_delay_seconds": 1200,  # Changed from default 900
        }

        result = await options_flow.async_step_init(user_input=user_input)

        assert result["type"] == FlowResultType.CREATE_ENTRY

    @pytest.mark.asyncio
    async def test_options_validates_power_sensors(
        self, options_flow: TeslaSolarChargerOptionsFlow, mock_hass: MagicMock
    ):
        """Test options flow validates power sensor units."""
        mock_hass.states.get = MagicMock(return_value=State(
            "sensor.invalid", "100", {"unit_of_measurement": "°C"}
        ))

        user_input = {
            "name": "Tesla",
            "production_sensor": "sensor.invalid",
            "consumption_sensors": ["sensor.invalid"],
            "consumption_excludes_charging": False,
            "amps_number": "number.tesla_charging_amps",
            "charging_switch": "switch.tesla_charging",
            "charging_state_sensor": "sensor.tesla_charging_state",
            "voltage": 230,
            "update_interval_seconds": 30,
            "min_amps": 5,
            "max_amps": 32,
            "margin_w": 0,
            "min_solar_generation_w": 200,
            "stop_delay_seconds": 360,
            "restart_delay_seconds": 900,
        }

        result = await options_flow.async_step_init(user_input=user_input)

        assert result["type"] == FlowResultType.FORM
        assert "production_sensor" in result["errors"]

