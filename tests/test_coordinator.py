"""Tests for coordinator.py - Phase 3 (TDD).

These tests define the expected behavior of the coordinator.
They should FAIL until the coordinator is properly implemented.
"""
from __future__ import annotations

import time
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfPower, STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import HomeAssistant, State

from custom_components.tesla_solar_charger.const import (
    ControllerState,
    Mode,
    IEC_PLUGGED_IN_STATES,
    DEFAULT_MIN_AMPS,
    DEFAULT_MAX_AMPS,
    DEFAULT_VOLTAGE,
    DEFAULT_MARGIN_W,
    DEFAULT_STOP_DELAY_SECONDS,
    DEFAULT_RESTART_DELAY_SECONDS,
    DEFAULT_MIN_SOLAR_GENERATION_W,
)
from custom_components.tesla_solar_charger.coordinator import (
    TeslaSolarChargerCoordinator,
)


class TestReadPowerW:
    """Test _read_power_w helper method."""

    @pytest.fixture
    def coordinator(
        self, mock_hass: MagicMock, mock_config_entry: ConfigEntry
    ) -> TeslaSolarChargerCoordinator:
        """Create coordinator instance."""
        return TeslaSolarChargerCoordinator(mock_hass, mock_config_entry)

    def test_reads_watts_correctly(
        self, coordinator: TeslaSolarChargerCoordinator, mock_hass: MagicMock
    ):
        """Test reading a value in watts."""
        mock_hass.states.get = MagicMock(return_value=State(
            "sensor.power", "3000", {"unit_of_measurement": "W"}
        ))

        result = coordinator._read_power_w("sensor.power")

        assert result == 3000.0

    def test_converts_kilowatts_to_watts(
        self, coordinator: TeslaSolarChargerCoordinator, mock_hass: MagicMock
    ):
        """Test kW values are converted to W."""
        mock_hass.states.get = MagicMock(return_value=State(
            "sensor.power", "3.5", {"unit_of_measurement": "kW"}
        ))

        result = coordinator._read_power_w("sensor.power")

        assert result == 3500.0

    def test_returns_none_for_unavailable(
        self, coordinator: TeslaSolarChargerCoordinator, mock_hass: MagicMock
    ):
        """Test unavailable sensors return None."""
        mock_hass.states.get = MagicMock(return_value=State(
            "sensor.power", STATE_UNAVAILABLE, {"unit_of_measurement": "W"}
        ))

        result = coordinator._read_power_w("sensor.power")

        assert result is None

    def test_returns_none_for_unknown(
        self, coordinator: TeslaSolarChargerCoordinator, mock_hass: MagicMock
    ):
        """Test unknown sensors return None."""
        mock_hass.states.get = MagicMock(return_value=State(
            "sensor.power", STATE_UNKNOWN, {"unit_of_measurement": "W"}
        ))

        result = coordinator._read_power_w("sensor.power")

        assert result is None

    def test_returns_none_for_missing_entity(
        self, coordinator: TeslaSolarChargerCoordinator, mock_hass: MagicMock
    ):
        """Test missing entities return None."""
        mock_hass.states.get = MagicMock(return_value=None)

        result = coordinator._read_power_w("sensor.nonexistent")

        assert result is None

    def test_returns_none_for_non_numeric(
        self, coordinator: TeslaSolarChargerCoordinator, mock_hass: MagicMock
    ):
        """Test non-numeric values return None."""
        mock_hass.states.get = MagicMock(return_value=State(
            "sensor.power", "not_a_number", {"unit_of_measurement": "W"}
        ))

        result = coordinator._read_power_w("sensor.power")

        assert result is None


class TestReadPlugState:
    """Test _read_plug_state helper method."""

    @pytest.fixture
    def coordinator(
        self, mock_hass: MagicMock, mock_config_entry: ConfigEntry
    ) -> TeslaSolarChargerCoordinator:
        """Create coordinator instance."""
        return TeslaSolarChargerCoordinator(mock_hass, mock_config_entry)

    @pytest.mark.parametrize("state", list(IEC_PLUGGED_IN_STATES))
    def test_plugged_in_states(
        self, coordinator: TeslaSolarChargerCoordinator,
        mock_hass: MagicMock,
        state: str
    ):
        """Test all plugged-in states return True."""
        mock_hass.states.get = MagicMock(return_value=State(
            "sensor.tesla_charging_state", state, {}
        ))

        result = coordinator._read_plug_state()

        assert result is True, f"State '{state}' should be plugged in"

    @pytest.mark.parametrize("state", ["Disconnected", "NoPower", "Unknown"])
    def test_not_plugged_in_states(
        self, coordinator: TeslaSolarChargerCoordinator,
        mock_hass: MagicMock,
        state: str
    ):
        """Test not-plugged-in states return False."""
        mock_hass.states.get = MagicMock(return_value=State(
            "sensor.tesla_charging_state", state, {}
        ))

        result = coordinator._read_plug_state()

        assert result is False, f"State '{state}' should NOT be plugged in"

    def test_unavailable_returns_false(
        self, coordinator: TeslaSolarChargerCoordinator, mock_hass: MagicMock
    ):
        """Test unavailable sensor returns False (not plugged in)."""
        mock_hass.states.get = MagicMock(return_value=State(
            "sensor.tesla_charging_state", STATE_UNAVAILABLE, {}
        ))

        result = coordinator._read_plug_state()

        assert result is False

    def test_missing_entity_returns_false(
        self, coordinator: TeslaSolarChargerCoordinator, mock_hass: MagicMock
    ):
        """Test missing entity returns False."""
        mock_hass.states.get = MagicMock(return_value=None)

        result = coordinator._read_plug_state()

        assert result is False


class TestComputeExcessW:
    """Test _compute_excess_w calculation."""

    @pytest.fixture
    def coordinator(
        self, mock_hass: MagicMock, mock_config_entry: ConfigEntry
    ) -> TeslaSolarChargerCoordinator:
        """Create coordinator instance."""
        coord = TeslaSolarChargerCoordinator(mock_hass, mock_config_entry)
        coord._commanded_amps = 10  # Simulating 10A commanded
        return coord

    def test_basic_excess_calculation(
        self, coordinator: TeslaSolarChargerCoordinator, mock_hass: MagicMock
    ):
        """Test basic excess calculation when consumption includes charging.

        Formula: excess = production - (consumption - current_charge) - margin
        With 5000W production, 3000W consumption (including 2300W charging at 10A@230V):
        excess = 5000 - (3000 - 2300) - 0 = 4300W
        """
        def get_state(entity_id: str):
            if entity_id == "sensor.solar_production":
                return State(entity_id, "5000", {"unit_of_measurement": "W"})
            elif entity_id == "sensor.home_consumption":
                return State(entity_id, "3000", {"unit_of_measurement": "W"})
            return None

        mock_hass.states.get = MagicMock(side_effect=get_state)

        result = coordinator._compute_excess_w()

        # 5000 - (3000 - 2300) - 0 = 4300
        assert result == 4300.0

    def test_excess_with_margin(
        self, coordinator: TeslaSolarChargerCoordinator,
        mock_hass: MagicMock,
        mock_config_entry: ConfigEntry
    ):
        """Test excess calculation respects margin setting.

        With margin of 200W:
        excess = 5000 - (3000 - 2300) - 200 = 4100W
        """
        mock_config_entry.options["margin_w"] = 200

        def get_state(entity_id: str):
            if entity_id == "sensor.solar_production":
                return State(entity_id, "5000", {"unit_of_measurement": "W"})
            elif entity_id == "sensor.home_consumption":
                return State(entity_id, "3000", {"unit_of_measurement": "W"})
            return None

        mock_hass.states.get = MagicMock(side_effect=get_state)

        result = coordinator._compute_excess_w()

        assert result == 4100.0

    def test_excess_when_consumption_excludes_charging(
        self, coordinator: TeslaSolarChargerCoordinator,
        mock_hass: MagicMock,
        mock_config_entry: ConfigEntry
    ):
        """Test calculation when consumption does NOT include EV charging.

        When consumption_excludes_charging is True:
        excess = production - consumption - margin
        (Do NOT add back current_charge_w)
        """
        mock_config_entry.data["consumption_excludes_charging"] = True

        def get_state(entity_id: str):
            if entity_id == "sensor.solar_production":
                return State(entity_id, "5000", {"unit_of_measurement": "W"})
            elif entity_id == "sensor.home_consumption":
                return State(entity_id, "700", {"unit_of_measurement": "W"})
            return None

        mock_hass.states.get = MagicMock(side_effect=get_state)

        result = coordinator._compute_excess_w()

        # 5000 - 700 - 0 = 4300 (no adding back charging)
        assert result == 4300.0

    def test_returns_none_when_production_unavailable(
        self, coordinator: TeslaSolarChargerCoordinator, mock_hass: MagicMock
    ):
        """Test returns None when production sensor unavailable."""
        def get_state(entity_id: str):
            if entity_id == "sensor.solar_production":
                return State(entity_id, STATE_UNAVAILABLE, {"unit_of_measurement": "W"})
            elif entity_id == "sensor.home_consumption":
                return State(entity_id, "1000", {"unit_of_measurement": "W"})
            return None

        mock_hass.states.get = MagicMock(side_effect=get_state)

        result = coordinator._compute_excess_w()

        assert result is None

    def test_sums_multiple_consumption_sensors(
        self, coordinator: TeslaSolarChargerCoordinator,
        mock_hass: MagicMock,
        mock_config_entry: ConfigEntry
    ):
        """Test multiple consumption sensors are summed."""
        mock_config_entry.data["consumption_sensors"] = [
            "sensor.consumption_1",
            "sensor.consumption_2",
        ]

        def get_state(entity_id: str):
            states = {
                "sensor.solar_production": State(
                    entity_id, "5000", {"unit_of_measurement": "W"}
                ),
                "sensor.consumption_1": State(
                    entity_id, "1000", {"unit_of_measurement": "W"}
                ),
                "sensor.consumption_2": State(
                    entity_id, "500", {"unit_of_measurement": "W"}
                ),
            }
            return states.get(entity_id)

        mock_hass.states.get = MagicMock(side_effect=get_state)

        result = coordinator._compute_excess_w()

        # 5000 - (1500 - 2300) - 0 = 5800 (but capped to available)
        # Actually: 5000 - (1500 - 2300) - 0 = 5800
        assert result == 5800.0


class TestTargetAmpsCalculation:
    """Test target amps calculation."""

    @pytest.fixture
    def coordinator(
        self, mock_hass: MagicMock, mock_config_entry: ConfigEntry
    ) -> TeslaSolarChargerCoordinator:
        """Create coordinator instance."""
        return TeslaSolarChargerCoordinator(mock_hass, mock_config_entry)

    def test_basic_target_amps(self, coordinator: TeslaSolarChargerCoordinator):
        """Test target amps = floor(excess_w / voltage)."""
        # 2300W / 230V = 10A
        result = coordinator._compute_target_amps(2300.0)
        assert result == 10

    def test_target_amps_floors_down(self, coordinator: TeslaSolarChargerCoordinator):
        """Test target amps floors down to whole amps."""
        # 2500W / 230V = 10.87A -> 10A
        result = coordinator._compute_target_amps(2500.0)
        assert result == 10

    def test_target_amps_clamped_to_min(
        self, coordinator: TeslaSolarChargerCoordinator, mock_config_entry: ConfigEntry
    ):
        """Test target amps clamped to min_amps."""
        mock_config_entry.options["min_amps"] = 5

        # 500W / 230V = 2.17A -> clamped to 5A
        result = coordinator._compute_target_amps(500.0)
        assert result == 5

    def test_target_amps_clamped_to_max(
        self, coordinator: TeslaSolarChargerCoordinator, mock_config_entry: ConfigEntry
    ):
        """Test target amps clamped to max_amps."""
        mock_config_entry.options["max_amps"] = 16

        # 10000W / 230V = 43.5A -> clamped to 16A
        result = coordinator._compute_target_amps(10000.0)
        assert result == 16

    def test_target_amps_zero_returns_zero(
        self, coordinator: TeslaSolarChargerCoordinator
    ):
        """Test zero/negative excess returns 0."""
        result = coordinator._compute_target_amps(0.0)
        assert result == 0

        result = coordinator._compute_target_amps(-500.0)
        assert result == 0


class TestStateMachine:
    """Test state machine transitions."""

    @pytest.fixture
    def coordinator(
        self, mock_hass: MagicMock, mock_config_entry: ConfigEntry
    ) -> TeslaSolarChargerCoordinator:
        """Create coordinator instance."""
        return TeslaSolarChargerCoordinator(mock_hass, mock_config_entry)

    def test_initial_state_is_idle(
        self, coordinator: TeslaSolarChargerCoordinator
    ):
        """Test coordinator starts in IDLE state."""
        assert coordinator._controller_state == ControllerState.IDLE

    def test_disabled_when_mode_off(
        self, coordinator: TeslaSolarChargerCoordinator
    ):
        """Test state is DISABLED when mode is Off."""
        coordinator._mode = Mode.OFF
        coordinator._update_state_machine(plugged_in=True, excess_w=5000)

        assert coordinator._controller_state == ControllerState.DISABLED

    def test_disabled_when_master_disabled(
        self, coordinator: TeslaSolarChargerCoordinator
    ):
        """Test state is DISABLED when master enable is off."""
        coordinator._mode = Mode.SOLAR_ONLY
        coordinator._master_enabled = False
        coordinator._update_state_machine(plugged_in=True, excess_w=5000)

        assert coordinator._controller_state == ControllerState.DISABLED

    def test_idle_when_not_plugged_in(
        self, coordinator: TeslaSolarChargerCoordinator
    ):
        """Test state is IDLE when car not plugged in."""
        coordinator._mode = Mode.SOLAR_ONLY
        coordinator._master_enabled = True
        coordinator._update_state_machine(plugged_in=False, excess_w=5000)

        assert coordinator._controller_state == ControllerState.IDLE

    def test_tracking_when_solar_available(
        self, coordinator: TeslaSolarChargerCoordinator
    ):
        """Test state is TRACKING when excess solar available."""
        coordinator._mode = Mode.SOLAR_ONLY
        coordinator._master_enabled = True
        coordinator._update_state_machine(plugged_in=True, excess_w=3000)

        assert coordinator._controller_state == ControllerState.TRACKING

    def test_forced_when_charge_now(
        self, coordinator: TeslaSolarChargerCoordinator
    ):
        """Test state is FORCED when mode is Charge Now."""
        coordinator._mode = Mode.CHARGE_NOW
        coordinator._master_enabled = True
        coordinator._update_state_machine(plugged_in=True, excess_w=0)

        assert coordinator._controller_state == ControllerState.FORCED


class TestHysteresisTimers:
    """Test 6-minute stop and 15-minute restart timers."""

    @pytest.fixture
    def coordinator(
        self, mock_hass: MagicMock, mock_config_entry: ConfigEntry
    ) -> TeslaSolarChargerCoordinator:
        """Create coordinator instance."""
        coord = TeslaSolarChargerCoordinator(mock_hass, mock_config_entry)
        coord._mode = Mode.SOLAR_ONLY
        coord._master_enabled = True
        return coord

    def test_enters_stopping_state_when_excess_drops(
        self, coordinator: TeslaSolarChargerCoordinator
    ):
        """Test enters STOPPING when excess drops below threshold."""
        coordinator._controller_state = ControllerState.TRACKING
        coordinator._commanded_amps = 10

        # Excess drops to 0 - should start stop timer
        coordinator._update_state_machine(plugged_in=True, excess_w=0)

        assert coordinator._controller_state == ControllerState.STOPPING
        assert coordinator._stop_timer_start is not None

    def test_returns_to_tracking_if_excess_recovers(
        self, coordinator: TeslaSolarChargerCoordinator
    ):
        """Test returns to TRACKING if excess recovers during stop timer."""
        coordinator._controller_state = ControllerState.STOPPING
        coordinator._stop_timer_start = time.monotonic()

        # Excess recovers
        coordinator._update_state_machine(plugged_in=True, excess_w=3000)

        assert coordinator._controller_state == ControllerState.TRACKING
        assert coordinator._stop_timer_start is None

    def test_enters_cooldown_after_stop_timer_expires(
        self, coordinator: TeslaSolarChargerCoordinator,
        mock_config_entry: ConfigEntry
    ):
        """Test enters COOLDOWN after 6-minute stop timer expires."""
        mock_config_entry.options["stop_delay_seconds"] = 360

        coordinator._controller_state = ControllerState.STOPPING
        # Set timer to 7 minutes ago (expired)
        coordinator._stop_timer_start = time.monotonic() - 420

        coordinator._update_state_machine(plugged_in=True, excess_w=0)

        assert coordinator._controller_state == ControllerState.COOLDOWN
        assert coordinator._cooldown_timer_start is not None

    def test_stays_in_cooldown_during_restart_delay(
        self, coordinator: TeslaSolarChargerCoordinator,
        mock_config_entry: ConfigEntry
    ):
        """Test stays in COOLDOWN during 15-minute restart delay."""
        mock_config_entry.options["restart_delay_seconds"] = 900

        coordinator._controller_state = ControllerState.COOLDOWN
        # Set cooldown timer to 10 minutes ago (not yet expired)
        coordinator._cooldown_timer_start = time.monotonic() - 600

        # Even with excess available, stays in cooldown
        coordinator._update_state_machine(plugged_in=True, excess_w=5000)

        assert coordinator._controller_state == ControllerState.COOLDOWN

    def test_exits_cooldown_after_restart_delay(
        self, coordinator: TeslaSolarChargerCoordinator,
        mock_config_entry: ConfigEntry
    ):
        """Test exits COOLDOWN after 15-minute restart delay expires."""
        mock_config_entry.options["restart_delay_seconds"] = 900

        coordinator._controller_state = ControllerState.COOLDOWN
        # Set cooldown timer to 16 minutes ago (expired)
        coordinator._cooldown_timer_start = time.monotonic() - 960

        coordinator._update_state_machine(plugged_in=True, excess_w=5000)

        assert coordinator._controller_state == ControllerState.TRACKING

    def test_charge_now_bypasses_cooldown(
        self, coordinator: TeslaSolarChargerCoordinator
    ):
        """Test Charge Now mode bypasses cooldown timer."""
        coordinator._controller_state = ControllerState.COOLDOWN
        coordinator._cooldown_timer_start = time.monotonic()  # Just started

        coordinator._mode = Mode.CHARGE_NOW
        coordinator._update_state_machine(plugged_in=True, excess_w=0)

        assert coordinator._controller_state == ControllerState.FORCED

    def test_mode_change_cancels_stop_timer(
        self, coordinator: TeslaSolarChargerCoordinator
    ):
        """Test mode change cancels stop timer."""
        coordinator._controller_state = ControllerState.STOPPING
        coordinator._stop_timer_start = time.monotonic()

        coordinator._mode = Mode.SOLAR_PLUS_GRID
        coordinator._update_state_machine(plugged_in=True, excess_w=3000)

        assert coordinator._stop_timer_start is None


class TestSendCommands:
    """Test sending commands to ESPHome proxy."""

    @pytest.fixture
    def coordinator(
        self, mock_hass: MagicMock, mock_config_entry: ConfigEntry
    ) -> TeslaSolarChargerCoordinator:
        """Create coordinator instance."""
        return TeslaSolarChargerCoordinator(mock_hass, mock_config_entry)

    @pytest.mark.asyncio
    async def test_send_amps_calls_service(
        self, coordinator: TeslaSolarChargerCoordinator, mock_hass: MagicMock
    ):
        """Test _send_amps calls number.set_value service."""
        await coordinator._send_amps(10)

        mock_hass.services.async_call.assert_called_once_with(
            "number",
            "set_value",
            {"entity_id": "number.tesla_charging_amps", "value": 10},
            blocking=True,
        )

    @pytest.mark.asyncio
    async def test_send_amps_updates_commanded_amps(
        self, coordinator: TeslaSolarChargerCoordinator, mock_hass: MagicMock
    ):
        """Test _send_amps updates commanded_amps on success."""
        await coordinator._send_amps(15)

        assert coordinator._commanded_amps == 15
        assert coordinator._last_command_succeeded is True

    @pytest.mark.asyncio
    async def test_send_amps_skips_if_unchanged(
        self, coordinator: TeslaSolarChargerCoordinator, mock_hass: MagicMock
    ):
        """Test _send_amps skips if value unchanged."""
        coordinator._commanded_amps = 10

        await coordinator._send_amps(10)

        mock_hass.services.async_call.assert_not_called()

    @pytest.mark.asyncio
    async def test_send_amps_handles_failure(
        self, coordinator: TeslaSolarChargerCoordinator, mock_hass: MagicMock
    ):
        """Test _send_amps handles service call failure."""
        mock_hass.services.async_call = AsyncMock(side_effect=Exception("BLE error"))
        coordinator._commanded_amps = 5

        await coordinator._send_amps(10)

        # commanded_amps should NOT be updated on failure
        assert coordinator._commanded_amps == 5
        assert coordinator._last_command_succeeded is False

    @pytest.mark.asyncio
    async def test_send_switch_on(
        self, coordinator: TeslaSolarChargerCoordinator, mock_hass: MagicMock
    ):
        """Test _send_switch turns on charging."""
        coordinator._is_charging = False

        await coordinator._send_switch(on=True)

        mock_hass.services.async_call.assert_called_once_with(
            "switch",
            "turn_on",
            {"entity_id": "switch.tesla_charging"},
            blocking=True,
        )

    @pytest.mark.asyncio
    async def test_send_switch_off(
        self, coordinator: TeslaSolarChargerCoordinator, mock_hass: MagicMock
    ):
        """Test _send_switch turns off charging."""
        coordinator._is_charging = True

        await coordinator._send_switch(on=False)

        mock_hass.services.async_call.assert_called_once_with(
            "switch",
            "turn_off",
            {"entity_id": "switch.tesla_charging"},
            blocking=True,
        )

    @pytest.mark.asyncio
    async def test_send_switch_skips_if_unchanged(
        self, coordinator: TeslaSolarChargerCoordinator, mock_hass: MagicMock
    ):
        """Test _send_switch skips if state unchanged."""
        coordinator._is_charging = True

        await coordinator._send_switch(on=True)

        mock_hass.services.async_call.assert_not_called()


class TestSolarOnlyMode:
    """Test Solar Only mode behavior."""

    @pytest.fixture
    def coordinator(
        self, mock_hass: MagicMock, mock_config_entry: ConfigEntry
    ) -> TeslaSolarChargerCoordinator:
        """Create coordinator in Solar Only mode."""
        coord = TeslaSolarChargerCoordinator(mock_hass, mock_config_entry)
        coord._mode = Mode.SOLAR_ONLY
        coord._master_enabled = True
        return coord

    @pytest.mark.asyncio
    async def test_charges_when_excess_available(
        self, coordinator: TeslaSolarChargerCoordinator, mock_hass: MagicMock
    ):
        """Test charges when excess solar available."""
        def get_state(entity_id: str):
            states = {
                "sensor.solar_production": State(
                    entity_id, "5000", {"unit_of_measurement": "W"}
                ),
                "sensor.home_consumption": State(
                    entity_id, "1500", {"unit_of_measurement": "W"}
                ),
                "sensor.tesla_charging_state": State(
                    entity_id, "Stopped", {}
                ),
            }
            return states.get(entity_id)

        mock_hass.states.get = MagicMock(side_effect=get_state)

        data = await coordinator._async_update_data()

        assert data["controller_state"] == ControllerState.TRACKING.value
        assert data["target_amps"] > 0

    @pytest.mark.asyncio
    async def test_stops_when_excess_drops_below_minimum(
        self, coordinator: TeslaSolarChargerCoordinator,
        mock_hass: MagicMock,
        mock_config_entry: ConfigEntry
    ):
        """Test stops charging when excess drops below min_amps threshold."""
        mock_config_entry.options["min_amps"] = 5  # 5A * 230V = 1150W minimum
        coordinator._controller_state = ControllerState.TRACKING
        coordinator._commanded_amps = 5

        def get_state(entity_id: str):
            states = {
                "sensor.solar_production": State(
                    entity_id, "1500", {"unit_of_measurement": "W"}
                ),
                "sensor.home_consumption": State(
                    entity_id, "1000", {"unit_of_measurement": "W"}
                ),  # Only 500W excess - below min
                "sensor.tesla_charging_state": State(
                    entity_id, "Charging", {}
                ),
            }
            return states.get(entity_id)

        mock_hass.states.get = MagicMock(side_effect=get_state)

        data = await coordinator._async_update_data()

        # Should start stop timer (enter STOPPING state)
        assert data["controller_state"] == ControllerState.STOPPING.value


class TestSolarPlusGridMode:
    """Test Solar + Grid mode behavior."""

    @pytest.fixture
    def coordinator(
        self, mock_hass: MagicMock, mock_config_entry: ConfigEntry
    ) -> TeslaSolarChargerCoordinator:
        """Create coordinator in Solar + Grid mode."""
        coord = TeslaSolarChargerCoordinator(mock_hass, mock_config_entry)
        coord._mode = Mode.SOLAR_PLUS_GRID
        coord._master_enabled = True
        return coord

    @pytest.mark.asyncio
    async def test_continues_at_minimum_when_excess_drops(
        self, coordinator: TeslaSolarChargerCoordinator,
        mock_hass: MagicMock,
        mock_config_entry: ConfigEntry
    ):
        """Test continues at min amps when excess drops (grid supplements)."""
        mock_config_entry.options["min_amps"] = 5
        mock_config_entry.options["min_solar_generation_w"] = 200
        coordinator._controller_state = ControllerState.TRACKING

        def get_state(entity_id: str):
            states = {
                "sensor.solar_production": State(
                    entity_id, "1000", {"unit_of_measurement": "W"}
                ),  # Solar present but low
                "sensor.home_consumption": State(
                    entity_id, "800", {"unit_of_measurement": "W"}
                ),  # Only 200W excess
                "sensor.tesla_charging_state": State(
                    entity_id, "Charging", {}
                ),
            }
            return states.get(entity_id)

        mock_hass.states.get = MagicMock(side_effect=get_state)

        data = await coordinator._async_update_data()

        # Should continue at min amps, not stop
        assert data["controller_state"] == ControllerState.TRACKING.value
        assert data["target_amps"] >= 5

    @pytest.mark.asyncio
    async def test_stops_when_below_min_solar_generation(
        self, coordinator: TeslaSolarChargerCoordinator,
        mock_hass: MagicMock,
        mock_config_entry: ConfigEntry
    ):
        """Test stops when solar generation below threshold."""
        mock_config_entry.options["min_solar_generation_w"] = 200
        coordinator._controller_state = ControllerState.TRACKING

        def get_state(entity_id: str):
            states = {
                "sensor.solar_production": State(
                    entity_id, "100", {"unit_of_measurement": "W"}
                ),  # Below min_solar_generation
                "sensor.home_consumption": State(
                    entity_id, "50", {"unit_of_measurement": "W"}
                ),
                "sensor.tesla_charging_state": State(
                    entity_id, "Charging", {}
                ),
            }
            return states.get(entity_id)

        mock_hass.states.get = MagicMock(side_effect=get_state)

        data = await coordinator._async_update_data()

        # Should stop - not enough solar, even in Solar + Grid mode
        assert data["controller_state"] in [
            ControllerState.STOPPING.value,
            ControllerState.IDLE.value,
        ]


class TestChargeNowMode:
    """Test Charge Now mode behavior."""

    @pytest.fixture
    def coordinator(
        self, mock_hass: MagicMock, mock_config_entry: ConfigEntry
    ) -> TeslaSolarChargerCoordinator:
        """Create coordinator in Charge Now mode."""
        coord = TeslaSolarChargerCoordinator(mock_hass, mock_config_entry)
        coord._mode = Mode.CHARGE_NOW
        coord._master_enabled = True
        return coord

    @pytest.mark.asyncio
    async def test_charges_at_max_amps(
        self, coordinator: TeslaSolarChargerCoordinator,
        mock_hass: MagicMock,
        mock_config_entry: ConfigEntry
    ):
        """Test Charge Now charges at max amps."""
        mock_config_entry.options["max_amps"] = 32

        def get_state(entity_id: str):
            if entity_id == "sensor.tesla_charging_state":
                return State(entity_id, "Stopped", {})
            return State(entity_id, "0", {"unit_of_measurement": "W"})

        mock_hass.states.get = MagicMock(side_effect=get_state)

        data = await coordinator._async_update_data()

        assert data["controller_state"] == ControllerState.FORCED.value
        assert data["target_amps"] == 32

    @pytest.mark.asyncio
    async def test_ignores_solar(
        self, coordinator: TeslaSolarChargerCoordinator, mock_hass: MagicMock
    ):
        """Test Charge Now ignores solar availability."""
        def get_state(entity_id: str):
            if entity_id == "sensor.tesla_charging_state":
                return State(entity_id, "Stopped", {})
            # No solar, high consumption
            if entity_id == "sensor.solar_production":
                return State(entity_id, "0", {"unit_of_measurement": "W"})
            if entity_id == "sensor.home_consumption":
                return State(entity_id, "5000", {"unit_of_measurement": "W"})
            return None

        mock_hass.states.get = MagicMock(side_effect=get_state)

        data = await coordinator._async_update_data()

        # Should still charge at max despite no solar
        assert data["controller_state"] == ControllerState.FORCED.value


class TestEdgeCases:
    """Test edge cases and error handling."""

    @pytest.fixture
    def coordinator(
        self, mock_hass: MagicMock, mock_config_entry: ConfigEntry
    ) -> TeslaSolarChargerCoordinator:
        """Create coordinator instance."""
        coord = TeslaSolarChargerCoordinator(mock_hass, mock_config_entry)
        coord._mode = Mode.SOLAR_ONLY
        coord._master_enabled = True
        return coord

    @pytest.mark.asyncio
    async def test_holds_amps_when_sensor_unavailable(
        self, coordinator: TeslaSolarChargerCoordinator, mock_hass: MagicMock
    ):
        """Test holds commanded amps when sensors become unavailable."""
        coordinator._commanded_amps = 10
        coordinator._controller_state = ControllerState.TRACKING

        def get_state(entity_id: str):
            if entity_id == "sensor.solar_production":
                return State(entity_id, STATE_UNAVAILABLE, {"unit_of_measurement": "W"})
            if entity_id == "sensor.tesla_charging_state":
                return State(entity_id, "Charging", {})
            return State(entity_id, "1000", {"unit_of_measurement": "W"})

        mock_hass.states.get = MagicMock(side_effect=get_state)

        data = await coordinator._async_update_data()

        # Should hold current amps, not change
        assert data["commanded_amps"] == 10

    @pytest.mark.asyncio
    async def test_unplugging_returns_to_idle(
        self, coordinator: TeslaSolarChargerCoordinator, mock_hass: MagicMock
    ):
        """Test unplugging car returns to IDLE state."""
        coordinator._controller_state = ControllerState.TRACKING
        coordinator._commanded_amps = 15

        def get_state(entity_id: str):
            if entity_id == "sensor.tesla_charging_state":
                return State(entity_id, "Disconnected", {})
            return State(entity_id, "5000", {"unit_of_measurement": "W"})

        mock_hass.states.get = MagicMock(side_effect=get_state)

        data = await coordinator._async_update_data()

        assert data["controller_state"] == ControllerState.IDLE.value
        assert data["plugged_in"] is False

    @pytest.mark.asyncio
    async def test_plug_event_resets_timers(
        self, coordinator: TeslaSolarChargerCoordinator, mock_hass: MagicMock
    ):
        """Test plug/unplug event resets timers."""
        coordinator._controller_state = ControllerState.COOLDOWN
        coordinator._cooldown_timer_start = time.monotonic()

        # Unplug
        def get_state_unplugged(entity_id: str):
            if entity_id == "sensor.tesla_charging_state":
                return State(entity_id, "Disconnected", {})
            return State(entity_id, "5000", {"unit_of_measurement": "W"})

        mock_hass.states.get = MagicMock(side_effect=get_state_unplugged)
        await coordinator._async_update_data()

        # Cooldown timer should be cleared
        assert coordinator._cooldown_timer_start is None

