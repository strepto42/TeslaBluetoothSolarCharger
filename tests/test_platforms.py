"""Tests for platform entities - Phase 4 (TDD).

These tests define the expected behavior of platform entities.
"""
from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from custom_components.tesla_solar_charger.const import (
    DOMAIN,
    Mode,
    ControllerState,
    DEFAULT_MIN_AMPS,
    DEFAULT_MAX_AMPS,
    DEFAULT_MARGIN_W,
)


class TestModeSelectEntity:
    """Test mode select entity."""

    @pytest.mark.asyncio
    async def test_has_correct_options(self, mock_hass: MagicMock):
        """Test select entity has all four mode options."""
        from custom_components.tesla_solar_charger.select import TeslaSolarChargerModeSelect

        # Create a mock coordinator
        coordinator = MagicMock()
        coordinator.data = {"mode": Mode.OFF.value}
        coordinator.mode = Mode.OFF

        entry = MagicMock()
        entry.entry_id = "test"

        select = TeslaSolarChargerModeSelect(coordinator, entry)

        assert "Off" in select.options
        assert "Solar Only" in select.options
        assert "Solar + Grid" in select.options
        assert "Charge Now" in select.options
        assert len(select.options) == 4

    @pytest.mark.asyncio
    async def test_current_option_reflects_coordinator(self, mock_hass: MagicMock):
        """Test current option reflects coordinator mode."""
        from custom_components.tesla_solar_charger.select import TeslaSolarChargerModeSelect

        coordinator = MagicMock()
        coordinator.data = {"mode": Mode.SOLAR_ONLY.value}
        coordinator.mode = Mode.SOLAR_ONLY

        entry = MagicMock()
        entry.entry_id = "test"

        select = TeslaSolarChargerModeSelect(coordinator, entry)

        assert select.current_option == "Solar Only"

    @pytest.mark.asyncio
    async def test_select_option_updates_coordinator(self, mock_hass: MagicMock):
        """Test selecting option updates coordinator and triggers refresh."""
        from custom_components.tesla_solar_charger.select import TeslaSolarChargerModeSelect

        coordinator = MagicMock()
        coordinator.data = {"mode": Mode.OFF.value}
        coordinator.mode = Mode.OFF
        coordinator.async_request_refresh = AsyncMock()

        entry = MagicMock()
        entry.entry_id = "test"

        select = TeslaSolarChargerModeSelect(coordinator, entry)
        select.hass = mock_hass

        await select.async_select_option("Solar Only")

        assert coordinator.mode == Mode.SOLAR_ONLY
        coordinator.async_request_refresh.assert_called_once()

    @pytest.mark.asyncio
    async def test_unique_id_format(self, mock_hass: MagicMock):
        """Test unique_id follows format {entry_id}_{key}."""
        from custom_components.tesla_solar_charger.select import TeslaSolarChargerModeSelect

        coordinator = MagicMock()
        coordinator.data = {"mode": Mode.OFF.value}

        entry = MagicMock()
        entry.entry_id = "abc123"

        select = TeslaSolarChargerModeSelect(coordinator, entry)

        assert select.unique_id == "abc123_mode"


class TestMasterEnableSwitch:
    """Test master enable switch entity."""

    @pytest.mark.asyncio
    async def test_is_on_reflects_coordinator(self, mock_hass: MagicMock):
        """Test switch state reflects coordinator master_enabled."""
        from custom_components.tesla_solar_charger.switch import TeslaSolarChargerMasterSwitch

        coordinator = MagicMock()
        coordinator.master_enabled = True
        coordinator.data = {}

        entry = MagicMock()
        entry.entry_id = "test"

        switch = TeslaSolarChargerMasterSwitch(coordinator, entry)

        assert switch.is_on is True

    @pytest.mark.asyncio
    async def test_turn_on_updates_coordinator(self, mock_hass: MagicMock):
        """Test turning on updates coordinator."""
        from custom_components.tesla_solar_charger.switch import TeslaSolarChargerMasterSwitch

        coordinator = MagicMock()
        coordinator.master_enabled = False
        coordinator.data = {}
        coordinator.async_request_refresh = AsyncMock()

        entry = MagicMock()
        entry.entry_id = "test"

        switch = TeslaSolarChargerMasterSwitch(coordinator, entry)
        switch.hass = mock_hass

        await switch.async_turn_on()

        assert coordinator.master_enabled is True
        coordinator.async_request_refresh.assert_called_once()

    @pytest.mark.asyncio
    async def test_turn_off_updates_coordinator(self, mock_hass: MagicMock):
        """Test turning off updates coordinator."""
        from custom_components.tesla_solar_charger.switch import TeslaSolarChargerMasterSwitch

        coordinator = MagicMock()
        coordinator.master_enabled = True
        coordinator.data = {}
        coordinator.async_request_refresh = AsyncMock()

        entry = MagicMock()
        entry.entry_id = "test"

        switch = TeslaSolarChargerMasterSwitch(coordinator, entry)
        switch.hass = mock_hass

        await switch.async_turn_off()

        assert coordinator.master_enabled is False
        coordinator.async_request_refresh.assert_called_once()


class TestDiagnosticSensors:
    """Test diagnostic sensor entities."""

    @pytest.mark.asyncio
    async def test_target_amps_sensor(self, mock_hass: MagicMock):
        """Test target amps sensor."""
        from custom_components.tesla_solar_charger.sensor import TeslaSolarChargerTargetAmpsSensor

        coordinator = MagicMock()
        coordinator.data = {"target_amps": 15}

        entry = MagicMock()
        entry.entry_id = "test"

        sensor = TeslaSolarChargerTargetAmpsSensor(coordinator, entry)

        assert sensor.native_value == 15
        assert sensor.native_unit_of_measurement == "A"

    @pytest.mark.asyncio
    async def test_commanded_amps_sensor(self, mock_hass: MagicMock):
        """Test commanded amps sensor."""
        from custom_components.tesla_solar_charger.sensor import TeslaSolarChargerCommandedAmpsSensor

        coordinator = MagicMock()
        coordinator.data = {"commanded_amps": 10}

        entry = MagicMock()
        entry.entry_id = "test"

        sensor = TeslaSolarChargerCommandedAmpsSensor(coordinator, entry)

        assert sensor.native_value == 10
        assert sensor.native_unit_of_measurement == "A"

    @pytest.mark.asyncio
    async def test_excess_solar_sensor(self, mock_hass: MagicMock):
        """Test excess solar sensor."""
        from custom_components.tesla_solar_charger.sensor import TeslaSolarChargerExcessSolarSensor

        coordinator = MagicMock()
        coordinator.data = {"excess_w": 2500.0}

        entry = MagicMock()
        entry.entry_id = "test"

        sensor = TeslaSolarChargerExcessSolarSensor(coordinator, entry)

        assert sensor.native_value == 2500.0
        assert sensor.native_unit_of_measurement == "W"
        assert sensor.device_class == "power"

    @pytest.mark.asyncio
    async def test_controller_state_sensor(self, mock_hass: MagicMock):
        """Test controller state sensor."""
        from custom_components.tesla_solar_charger.sensor import TeslaSolarChargerStateSensor

        coordinator = MagicMock()
        coordinator.data = {"controller_state": ControllerState.TRACKING.value}

        entry = MagicMock()
        entry.entry_id = "test"

        sensor = TeslaSolarChargerStateSensor(coordinator, entry)

        assert sensor.native_value == "tracking"

    @pytest.mark.asyncio
    async def test_seconds_until_transition_sensor(self, mock_hass: MagicMock):
        """Test seconds until transition sensor."""
        from custom_components.tesla_solar_charger.sensor import TeslaSolarChargerTransitionSensor

        coordinator = MagicMock()
        coordinator.data = {"seconds_until_next_transition": 120}

        entry = MagicMock()
        entry.entry_id = "test"

        sensor = TeslaSolarChargerTransitionSensor(coordinator, entry)

        assert sensor.native_value == 120
        assert sensor.native_unit_of_measurement == "s"


class TestBinarySensors:
    """Test binary_sensor entities (plugged_in, is_charging, last_command_succeeded)."""

    @pytest.mark.asyncio
    async def test_plugged_in_binary_sensor(self, mock_hass: MagicMock):
        """plugged_in is a binary sensor (is_on: bool), not a string sensor."""
        from custom_components.tesla_solar_charger.binary_sensor import (
            TeslaSolarChargerPluggedInBinarySensor,
        )

        coordinator = MagicMock()
        coordinator.data = {"plugged_in": True}
        entry = MagicMock()
        entry.entry_id = "test"

        sensor = TeslaSolarChargerPluggedInBinarySensor(coordinator, entry)
        assert sensor.is_on is True

        coordinator.data = {"plugged_in": False}
        assert sensor.is_on is False

    @pytest.mark.asyncio
    async def test_is_charging_binary_sensor(self, mock_hass: MagicMock):
        """is_charging is a binary sensor."""
        from custom_components.tesla_solar_charger.binary_sensor import (
            TeslaSolarChargerIsChargingBinarySensor,
        )

        coordinator = MagicMock()
        coordinator.data = {"is_charging": True}
        entry = MagicMock()
        entry.entry_id = "test"

        sensor = TeslaSolarChargerIsChargingBinarySensor(coordinator, entry)
        assert sensor.is_on is True

    @pytest.mark.asyncio
    async def test_last_command_succeeded_binary_sensor(self, mock_hass: MagicMock):
        """last_command_succeeded is a binary sensor with None handling."""
        from custom_components.tesla_solar_charger.binary_sensor import (
            TeslaSolarChargerLastCommandBinarySensor,
        )

        coordinator = MagicMock()
        coordinator.data = {"last_command_succeeded": True}
        entry = MagicMock()
        entry.entry_id = "test"

        sensor = TeslaSolarChargerLastCommandBinarySensor(coordinator, entry)
        assert sensor.is_on is True

        coordinator.data = {"last_command_succeeded": False}
        assert sensor.is_on is False

        # No command sent yet → unknown (is_on returns None)
        coordinator.data = {"last_command_succeeded": None}
        assert sensor.is_on is None


class TestBatteryDiagnosticEntities:
    """Battery awareness exposes three diagnostic entities."""

    @pytest.mark.asyncio
    async def test_battery_power_sensor(self, mock_hass: MagicMock):
        from custom_components.tesla_solar_charger.sensor import (
            TeslaSolarChargerBatteryPowerSensor,
        )

        coordinator = MagicMock()
        coordinator.data = {"battery_power_w": 1500.0}
        entry = MagicMock()
        entry.entry_id = "test"

        sensor = TeslaSolarChargerBatteryPowerSensor(coordinator, entry)
        assert sensor.native_value == 1500.0
        assert sensor.native_unit_of_measurement == "W"

    @pytest.mark.asyncio
    async def test_battery_soc_sensor(self, mock_hass: MagicMock):
        from custom_components.tesla_solar_charger.sensor import (
            TeslaSolarChargerBatterySocSensor,
        )

        coordinator = MagicMock()
        coordinator.data = {"battery_soc_pct": 75.0}
        entry = MagicMock()
        entry.entry_id = "test"

        sensor = TeslaSolarChargerBatterySocSensor(coordinator, entry)
        assert sensor.native_value == 75.0
        assert sensor.native_unit_of_measurement == "%"

    @pytest.mark.asyncio
    async def test_battery_priority_binary_sensor(self, mock_hass: MagicMock):
        from custom_components.tesla_solar_charger.binary_sensor import (
            TeslaSolarChargerBatteryPriorityBinarySensor,
        )

        coordinator = MagicMock()
        coordinator.data = {"battery_priority_active": True}
        entry = MagicMock()
        entry.entry_id = "test"

        sensor = TeslaSolarChargerBatteryPriorityBinarySensor(coordinator, entry)
        assert sensor.is_on is True

        coordinator.data = {"battery_priority_active": False}
        assert sensor.is_on is False


class TestSensorPlatformDoesNotExposeBooleanSensors:
    """The sensor platform should no longer export plugged_in/is_charging/last_command."""

    def test_string_boolean_sensors_removed(self):
        """Old string-based boolean sensor classes should not exist on sensor.py."""
        from custom_components.tesla_solar_charger import sensor

        assert not hasattr(sensor, "TeslaSolarChargerPluggedInSensor")
        assert not hasattr(sensor, "TeslaSolarChargerIsChargingSensor")
        assert not hasattr(sensor, "TeslaSolarChargerLastCommandSensor")


class TestNumberEntities:
    """Test number entities for settings."""

    @pytest.mark.asyncio
    async def test_min_amps_number(self, mock_hass: MagicMock):
        """Test min amps number entity."""
        from custom_components.tesla_solar_charger.number import TeslaSolarChargerMinAmpsNumber

        coordinator = MagicMock()
        coordinator.data = {}

        entry = MagicMock()
        entry.entry_id = "test"
        entry.options = {"min_amps": 6}

        number = TeslaSolarChargerMinAmpsNumber(coordinator, entry)

        assert number.native_value == 6
        assert number.native_min_value == 1
        assert number.native_max_value == 32
        assert number.native_unit_of_measurement == "A"

    @pytest.mark.asyncio
    async def test_max_amps_number(self, mock_hass: MagicMock):
        """Test max amps number entity."""
        from custom_components.tesla_solar_charger.number import TeslaSolarChargerMaxAmpsNumber

        coordinator = MagicMock()
        coordinator.data = {}

        entry = MagicMock()
        entry.entry_id = "test"
        entry.options = {"max_amps": 16}

        number = TeslaSolarChargerMaxAmpsNumber(coordinator, entry)

        assert number.native_value == 16

    @pytest.mark.asyncio
    async def test_margin_number(self, mock_hass: MagicMock):
        """Test margin number entity."""
        from custom_components.tesla_solar_charger.number import TeslaSolarChargerMarginNumber

        coordinator = MagicMock()
        coordinator.data = {}

        entry = MagicMock()
        entry.entry_id = "test"
        entry.options = {"margin_w": 100}

        number = TeslaSolarChargerMarginNumber(coordinator, entry)

        assert number.native_value == 100
        assert number.native_min_value == -5000
        assert number.native_max_value == 5000
        assert number.native_unit_of_measurement == "W"

    @pytest.mark.asyncio
    async def test_set_value_updates_options(
        self, mock_hass: MagicMock, mock_config_entry: ConfigEntry
    ):
        """Test setting value updates config entry options."""
        from custom_components.tesla_solar_charger.number import TeslaSolarChargerMinAmpsNumber

        coordinator = MagicMock()
        coordinator.data = {}
        coordinator.async_request_refresh = AsyncMock()

        mock_config_entry.options = {"min_amps": 5}

        number = TeslaSolarChargerMinAmpsNumber(coordinator, mock_config_entry)
        number.hass = mock_hass

        await number.async_set_native_value(8)

        # Should update options and refresh
        mock_hass.config_entries.async_update_entry.assert_called()
        coordinator.async_request_refresh.assert_called_once()


class TestDeviceInfo:
    """Test device info grouping."""

    @pytest.mark.asyncio
    async def test_entities_share_device(self, mock_hass: MagicMock):
        """Test all entities share the same device."""
        from custom_components.tesla_solar_charger.select import TeslaSolarChargerModeSelect
        from custom_components.tesla_solar_charger.switch import TeslaSolarChargerMasterSwitch
        from custom_components.tesla_solar_charger.sensor import TeslaSolarChargerTargetAmpsSensor

        coordinator = MagicMock()
        coordinator.data = {"mode": Mode.OFF.value, "target_amps": 0}
        coordinator.mode = Mode.OFF
        coordinator.master_enabled = True

        entry = MagicMock()
        entry.entry_id = "test123"
        entry.title = "Tesla Solar Charger"

        select = TeslaSolarChargerModeSelect(coordinator, entry)
        switch = TeslaSolarChargerMasterSwitch(coordinator, entry)
        sensor = TeslaSolarChargerTargetAmpsSensor(coordinator, entry)

        # All should have device_info with same identifiers
        assert select.device_info is not None
        assert switch.device_info is not None
        assert sensor.device_info is not None

        assert select.device_info["identifiers"] == switch.device_info["identifiers"]
        assert switch.device_info["identifiers"] == sensor.device_info["identifiers"]

