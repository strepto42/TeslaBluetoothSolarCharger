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
        """Options flow accepts entity bindings + timing settings.

        min_amps/max_amps/margin_w are NOT in the options flow — they're
        controlled by NumberEntity widgets on the dashboard.
        """
        user_input = {
            "name": "Tesla Solar Charger",
            "production_sensor": "sensor.solar_production",
            "consumption_sensors": ["sensor.home_consumption"],
            "consumption_excludes_charging": False,
            "amps_number": "number.tesla_charging_amps",
            "charging_switch": "switch.tesla_charging",
            "charging_state_sensor": "sensor.tesla_charging_state",
            "voltage": 230,
            "update_interval_seconds": 60,
            "min_solar_generation_w": 300,
            "stop_delay_seconds": 480,
            "restart_delay_seconds": 1200,
        }

        result = await options_flow.async_step_init(user_input=user_input)

        assert result["type"] == FlowResultType.CREATE_ENTRY

    @pytest.mark.asyncio
    async def test_options_save_separates_data_and_options(
        self, options_flow: TeslaSolarChargerOptionsFlow,
        mock_hass: MagicMock,
        mock_config_entry: ConfigEntry,
    ):
        """Entity bindings save to entry.data; entry.options preserved verbatim.

        The options flow only edits entity bindings now — runtime tunables
        live on dashboard NumberEntity / SelectEntity controls and are
        written directly to entry.options by those entities. The options
        flow's save path must preserve entry.options unchanged.
        """
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

        await options_flow.async_step_init(user_input=user_input)

        call = mock_hass.config_entries.async_update_entry.call_args
        saved_data = call.kwargs["data"]
        saved_options = call.kwargs["options"]

        # Bindings live in data
        assert saved_data["production_sensor"] == "sensor.solar_production"
        assert saved_data["amps_number"] == "number.tesla_charging_amps"
        assert saved_data["voltage"] == 230
        # Tunables don't leak into data
        assert "update_interval_seconds" not in saved_data
        # Pre-existing options preserved verbatim
        assert saved_options["update_interval_seconds"] == 30
        assert saved_options["stop_delay_seconds"] == 360
        # Bindings don't leak into options
        assert "production_sensor" not in saved_options
        assert "amps_number" not in saved_options

    @pytest.mark.asyncio
    async def test_options_save_preserves_number_entity_settings(
        self, options_flow: TeslaSolarChargerOptionsFlow,
        mock_hass: MagicMock,
        mock_config_entry: ConfigEntry,
    ):
        """Saving the options flow must not clobber options written by NumberEntity widgets.

        min_amps/max_amps/margin_w are written to entry.options by the
        dashboard NumberEntity setters. The options flow does not expose
        them, but saving the flow must preserve them.
        """
        # Pretend the user previously tuned min_amps via the dashboard widget
        mock_config_entry.options = {
            **mock_config_entry.options,
            "min_amps": 8,
            "max_amps": 24,
            "margin_w": 250,
        }

        user_input = {
            "name": "Tesla",
            "production_sensor": "sensor.solar_production",
            "consumption_sensors": ["sensor.home_consumption"],
            "consumption_excludes_charging": False,
            "amps_number": "number.tesla_charging_amps",
            "charging_switch": "switch.tesla_charging",
            "charging_state_sensor": "sensor.tesla_charging_state",
            "voltage": 230,
            "update_interval_seconds": 60,
            "min_solar_generation_w": 300,
            "stop_delay_seconds": 480,
            "restart_delay_seconds": 1200,
        }

        await options_flow.async_step_init(user_input=user_input)

        saved_options = mock_hass.config_entries.async_update_entry.call_args.kwargs[
            "options"
        ]
        assert saved_options["min_amps"] == 8
        assert saved_options["max_amps"] == 24
        assert saved_options["margin_w"] == 250

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


def _valid_battery_sensors_state(entity_id: str) -> State | None:
    """States for a fully-valid setup with battery sensors."""
    matrix = {
        "sensor.solar_production": ("3000", "W"),
        "sensor.home_consumption": ("1500", "W"),
        "sensor.battery_power": ("500", "W"),
        "sensor.battery_soc": ("75", "%"),
    }
    if entity_id in matrix:
        value, unit = matrix[entity_id]
        return State(entity_id, value, {"unit_of_measurement": unit})
    return None


class TestBatteryAwarenessConfigFlow:
    """Tests for the new battery-aware config-flow fields."""

    @pytest.fixture
    def flow(self, mock_hass: MagicMock) -> TeslaSolarChargerConfigFlow:
        flow = TeslaSolarChargerConfigFlow()
        flow.hass = mock_hass
        return flow

    @pytest.fixture
    def options_flow(
        self, mock_hass: MagicMock, mock_config_entry: ConfigEntry
    ) -> TeslaSolarChargerOptionsFlow:
        flow = TeslaSolarChargerOptionsFlow()
        flow.hass = mock_hass
        flow.handler = mock_config_entry.entry_id
        mock_hass.config_entries.async_get_known_entry = MagicMock(
            return_value=mock_config_entry
        )
        return flow

    @pytest.mark.asyncio
    async def test_accepts_battery_sensor_pair(
        self, flow: TeslaSolarChargerConfigFlow, mock_hass: MagicMock
    ):
        """Both battery sensors set, both valid units → entry created."""
        mock_hass.states.get = MagicMock(side_effect=_valid_battery_sensors_state)

        user_input = {
            "name": "Tesla",
            "production_sensor": "sensor.solar_production",
            "consumption_sensors": ["sensor.home_consumption"],
            "consumption_excludes_charging": False,
            "amps_number": "number.tesla_charging_amps",
            "charging_switch": "switch.tesla_charging",
            "charging_state_sensor": "sensor.tesla_charging_state",
            "voltage": 230,
            "battery_power_sensor": "sensor.battery_power",
            "battery_soc_sensor": "sensor.battery_soc",
            "battery_power_positive_is_charging": True,
        }

        result = await flow.async_step_user(user_input=user_input)

        assert result["type"] == FlowResultType.CREATE_ENTRY
        assert result["data"]["battery_power_sensor"] == "sensor.battery_power"
        assert result["data"]["battery_soc_sensor"] == "sensor.battery_soc"

    @pytest.mark.asyncio
    async def test_accepts_no_battery_sensors(
        self, flow: TeslaSolarChargerConfigFlow, mock_hass: MagicMock
    ):
        """Neither battery sensor set → entry created (battery awareness off)."""
        def get_state(entity_id: str):
            if entity_id == "sensor.solar_production":
                return State(entity_id, "3000", {"unit_of_measurement": "W"})
            if entity_id == "sensor.home_consumption":
                return State(entity_id, "1500", {"unit_of_measurement": "W"})
            return None

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
    async def test_rejects_only_power_sensor_set(
        self, flow: TeslaSolarChargerConfigFlow, mock_hass: MagicMock
    ):
        """Power set without SoC → battery_pair_incomplete error."""
        mock_hass.states.get = MagicMock(side_effect=_valid_battery_sensors_state)

        user_input = {
            "name": "Tesla",
            "production_sensor": "sensor.solar_production",
            "consumption_sensors": ["sensor.home_consumption"],
            "consumption_excludes_charging": False,
            "amps_number": "number.tesla_charging_amps",
            "charging_switch": "switch.tesla_charging",
            "charging_state_sensor": "sensor.tesla_charging_state",
            "voltage": 230,
            "battery_power_sensor": "sensor.battery_power",
            # battery_soc_sensor intentionally missing
        }

        result = await flow.async_step_user(user_input=user_input)
        assert result["type"] == FlowResultType.FORM
        assert result["errors"].get("battery_soc_sensor") == "battery_pair_incomplete"

    @pytest.mark.asyncio
    async def test_rejects_only_soc_sensor_set(
        self, flow: TeslaSolarChargerConfigFlow, mock_hass: MagicMock
    ):
        """SoC set without power → battery_pair_incomplete error."""
        mock_hass.states.get = MagicMock(side_effect=_valid_battery_sensors_state)

        user_input = {
            "name": "Tesla",
            "production_sensor": "sensor.solar_production",
            "consumption_sensors": ["sensor.home_consumption"],
            "consumption_excludes_charging": False,
            "amps_number": "number.tesla_charging_amps",
            "charging_switch": "switch.tesla_charging",
            "charging_state_sensor": "sensor.tesla_charging_state",
            "voltage": 230,
            "battery_soc_sensor": "sensor.battery_soc",
            # battery_power_sensor intentionally missing
        }

        result = await flow.async_step_user(user_input=user_input)
        assert result["type"] == FlowResultType.FORM
        assert result["errors"].get("battery_power_sensor") == "battery_pair_incomplete"

    @pytest.mark.asyncio
    async def test_rejects_battery_power_sensor_with_wrong_unit(
        self, flow: TeslaSolarChargerConfigFlow, mock_hass: MagicMock
    ):
        """Battery power sensor must be W or kW."""
        def get_state(entity_id: str):
            if entity_id == "sensor.solar_production":
                return State(entity_id, "3000", {"unit_of_measurement": "W"})
            if entity_id == "sensor.home_consumption":
                return State(entity_id, "1500", {"unit_of_measurement": "W"})
            if entity_id == "sensor.battery_power":
                # wrong unit (volts instead of watts)
                return State(entity_id, "500", {"unit_of_measurement": "V"})
            if entity_id == "sensor.battery_soc":
                return State(entity_id, "75", {"unit_of_measurement": "%"})
            return None

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
            "battery_power_sensor": "sensor.battery_power",
            "battery_soc_sensor": "sensor.battery_soc",
        }

        result = await flow.async_step_user(user_input=user_input)
        assert result["type"] == FlowResultType.FORM
        assert result["errors"].get("battery_power_sensor") == "invalid_power_unit"

    @pytest.mark.asyncio
    async def test_rejects_battery_soc_sensor_with_wrong_unit(
        self, flow: TeslaSolarChargerConfigFlow, mock_hass: MagicMock
    ):
        """Battery SoC sensor must report in %."""
        def get_state(entity_id: str):
            if entity_id == "sensor.solar_production":
                return State(entity_id, "3000", {"unit_of_measurement": "W"})
            if entity_id == "sensor.home_consumption":
                return State(entity_id, "1500", {"unit_of_measurement": "W"})
            if entity_id == "sensor.battery_power":
                return State(entity_id, "500", {"unit_of_measurement": "W"})
            if entity_id == "sensor.battery_soc":
                # wrong unit
                return State(entity_id, "75", {"unit_of_measurement": "kWh"})
            return None

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
            "battery_power_sensor": "sensor.battery_power",
            "battery_soc_sensor": "sensor.battery_soc",
        }

        result = await flow.async_step_user(user_input=user_input)
        assert result["type"] == FlowResultType.FORM
        assert result["errors"].get("battery_soc_sensor") == "invalid_battery_soc_unit"

    @pytest.mark.asyncio
    async def test_moved_tunables_skipped_by_options_flow(
        self,
        options_flow: TeslaSolarChargerOptionsFlow,
        mock_hass: MagicMock,
        mock_config_entry: ConfigEntry,
    ):
        """5 tunables + battery_priority_style live on entities now.

        Submitting them through the options flow should be ignored: the
        save path must not write them to entry.options (they're owned by
        their respective NumberEntity/SelectEntity setters). Pre-existing
        values written by the entities must be preserved.
        """
        mock_hass.states.get = MagicMock(side_effect=_valid_battery_sensors_state)

        # Pretend the user previously tuned these via the dashboard widgets
        mock_config_entry.options = {
            **mock_config_entry.options,
            "update_interval_seconds": 45,
            "min_solar_generation_w": 250,
            "stop_delay_seconds": 480,
            "restart_delay_seconds": 1200,
            "battery_priority_charge_limit_pct": 65,
            "battery_priority_style": "graduated",
        }

        # User submits the options form. Even if a misbehaving caller
        # pushes these legacy keys, the save path drops them.
        user_input = {
            "name": "Tesla",
            "production_sensor": "sensor.solar_production",
            "consumption_sensors": ["sensor.home_consumption"],
            "consumption_excludes_charging": False,
            "amps_number": "number.tesla_charging_amps",
            "charging_switch": "switch.tesla_charging",
            "charging_state_sensor": "sensor.tesla_charging_state",
            "voltage": 230,
            "battery_power_sensor": "sensor.battery_power",
            "battery_soc_sensor": "sensor.battery_soc",
            "battery_power_positive_is_charging": True,
            # Legacy keys a user might still send through:
            "update_interval_seconds": 99,
            "stop_delay_seconds": 99,
        }

        await options_flow.async_step_init(user_input=user_input)

        saved_options = mock_hass.config_entries.async_update_entry.call_args.kwargs[
            "options"
        ]
        # Pre-existing values preserved, not overwritten by submitted input
        assert saved_options["update_interval_seconds"] == 45
        assert saved_options["stop_delay_seconds"] == 480
        assert saved_options["min_solar_generation_w"] == 250
        assert saved_options["restart_delay_seconds"] == 1200
        assert saved_options["battery_priority_charge_limit_pct"] == 65
        assert saved_options["battery_priority_style"] == "graduated"

    @pytest.mark.asyncio
    async def test_options_flow_saves_battery_bindings(
        self,
        options_flow: TeslaSolarChargerOptionsFlow,
        mock_hass: MagicMock,
        mock_config_entry: ConfigEntry,
    ):
        """Battery sensor bindings + sign toggle save to entry.data.

        The reserve and style now live on a NumberEntity and a SelectEntity
        respectively, not the options flow.
        """
        mock_hass.states.get = MagicMock(side_effect=_valid_battery_sensors_state)

        user_input = {
            "name": "Tesla",
            "production_sensor": "sensor.solar_production",
            "consumption_sensors": ["sensor.home_consumption"],
            "consumption_excludes_charging": False,
            "amps_number": "number.tesla_charging_amps",
            "charging_switch": "switch.tesla_charging",
            "charging_state_sensor": "sensor.tesla_charging_state",
            "voltage": 230,
            "battery_power_sensor": "sensor.battery_power",
            "battery_soc_sensor": "sensor.battery_soc",
            "battery_power_positive_is_charging": False,
        }

        await options_flow.async_step_init(user_input=user_input)

        call = mock_hass.config_entries.async_update_entry.call_args
        saved_data = call.kwargs["data"]

        assert saved_data["battery_power_sensor"] == "sensor.battery_power"
        assert saved_data["battery_soc_sensor"] == "sensor.battery_soc"
        assert saved_data["battery_power_positive_is_charging"] is False

