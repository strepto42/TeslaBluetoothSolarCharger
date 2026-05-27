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


class TestProductionTreatedAsZero:
    """Test that unavailable production is treated as 0W."""

    @pytest.fixture
    def coordinator(
        self, mock_hass: MagicMock, mock_config_entry: ConfigEntry
    ) -> TeslaSolarChargerCoordinator:
        """Create coordinator instance."""
        return TeslaSolarChargerCoordinator(mock_hass, mock_config_entry)

    @pytest.mark.asyncio
    async def test_unavailable_production_treated_as_zero(
        self, coordinator: TeslaSolarChargerCoordinator,
        mock_hass: MagicMock
    ):
        """Test unavailable production sensor is treated as 0W."""
        coordinator._mode = Mode.SOLAR_ONLY
        coordinator._master_enabled = True

        def get_state(entity_id: str):
            if entity_id == "sensor.solar_production":
                # Production unavailable (e.g., inverter offline at night)
                return State(entity_id, STATE_UNAVAILABLE, {"unit_of_measurement": "W"})
            if entity_id == "sensor.home_consumption":
                return State(entity_id, "500", {"unit_of_measurement": "W"})
            if entity_id == "sensor.tesla_charging_state":
                return State(entity_id, "Stopped", {})
            return None

        mock_hass.states.get = MagicMock(side_effect=get_state)

        data = await coordinator._async_update_data()

        # Production should be 0 (treated as zero), not None
        assert data["production_w"] == 0.0
        # Excess should be calculated: 0 - 500 - 0 = -500W
        assert data["excess_w"] == -500.0

    @pytest.mark.asyncio
    async def test_solar_tracking_works_with_unavailable_production(
        self, coordinator: TeslaSolarChargerCoordinator,
        mock_hass: MagicMock
    ):
        """Test solar tracking works when production unavailable (will show no excess)."""
        coordinator._mode = Mode.SOLAR_ONLY
        coordinator._master_enabled = True

        def get_state(entity_id: str):
            if entity_id == "sensor.solar_production":
                return State(entity_id, STATE_UNAVAILABLE, {"unit_of_measurement": "W"})
            if entity_id == "sensor.home_consumption":
                return State(entity_id, "1000", {"unit_of_measurement": "W"})
            if entity_id == "sensor.tesla_charging_state":
                return State(entity_id, "Stopped", {})
            return None

        mock_hass.states.get = MagicMock(side_effect=get_state)

        data = await coordinator._async_update_data()

        # With 0 production and 1000W consumption, excess is negative
        # Controller should be IDLE (no excess to track)
        assert data["production_w"] == 0.0
        assert data["excess_w"] < 0


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


class TestComputeExcessWWithValues:
    """Test _compute_excess_w_with_values calculation (the live helper)."""

    @pytest.fixture
    def coordinator(
        self, mock_hass: MagicMock, mock_config_entry: ConfigEntry
    ) -> TeslaSolarChargerCoordinator:
        """Create coordinator with EV actively charging at 10A."""
        coord = TeslaSolarChargerCoordinator(mock_hass, mock_config_entry)
        coord._commanded_amps = 10  # Simulating 10A commanded
        coord._is_charging = True  # Switch is on, EV is actually drawing
        return coord

    def test_basic_excess_calculation(
        self, coordinator: TeslaSolarChargerCoordinator
    ):
        """Test basic excess when consumption includes charging.

        Formula: excess = production - (consumption - current_charge) - margin
        5000W production, 3000W consumption (incl. 2300W charging at 10A@230V):
        excess = 5000 - (3000 - 2300) - 0 = 4300W
        """
        result = coordinator._compute_excess_w_with_values(5000.0, 3000.0)
        assert result == 4300.0

    def test_excess_with_margin(
        self, coordinator: TeslaSolarChargerCoordinator,
        mock_config_entry: ConfigEntry,
    ):
        """Test excess calculation respects margin setting."""
        mock_config_entry.options["margin_w"] = 200
        result = coordinator._compute_excess_w_with_values(5000.0, 3000.0)
        # 5000 - (3000 - 2300) - 200 = 4100
        assert result == 4100.0

    def test_excess_when_consumption_excludes_charging(
        self, coordinator: TeslaSolarChargerCoordinator,
        mock_config_entry: ConfigEntry,
    ):
        """Consumption excludes EV → don't add charging back."""
        mock_config_entry.data["consumption_excludes_charging"] = True
        result = coordinator._compute_excess_w_with_values(5000.0, 700.0)
        # 5000 - 700 - 0 = 4300
        assert result == 4300.0

    def test_returns_none_when_consumption_unavailable(
        self, coordinator: TeslaSolarChargerCoordinator
    ):
        """Returns None when consumption is None (sensor unavailable)."""
        result = coordinator._compute_excess_w_with_values(5000.0, None)
        assert result is None

    def test_production_zero_treated_normally(
        self, coordinator: TeslaSolarChargerCoordinator
    ):
        """Production of 0 is a valid value, computes negative excess."""
        result = coordinator._compute_excess_w_with_values(0.0, 1000.0)
        # 0 - (1000 - 2300) - 0 = 1300 (consumption includes EV draw)
        assert result == 1300.0


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
        """Test zero/negative excess returns 0 (not min_amps)."""
        result = coordinator._compute_target_amps(0.0)
        assert result == 0

        result = coordinator._compute_target_amps(-500.0)
        assert result == 0

    def test_target_amps_positive_below_min_clamps_to_min(
        self, coordinator: TeslaSolarChargerCoordinator,
        mock_config_entry: ConfigEntry,
    ):
        """Positive excess below min_amps*voltage clamps up to min_amps.

        Per CLAUDE.md: target_amps clamped to [min_amps, max_amps].
        Zero is the only value below min_amps that survives — it signals
        "stop charging" rather than "charge at minimum".
        """
        mock_config_entry.options["min_amps"] = 5
        # 230W = 1A worth of excess, below min_amps (5)
        result = coordinator._compute_target_amps(230.0)
        assert result == 5


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
        coordinator._update_state_machine(plugged_in=True, excess_w=5000, production_w=0.0)

        assert coordinator._controller_state == ControllerState.DISABLED

    def test_disabled_when_master_disabled(
        self, coordinator: TeslaSolarChargerCoordinator
    ):
        """Test state is DISABLED when master enable is off."""
        coordinator._mode = Mode.SOLAR_ONLY
        coordinator._master_enabled = False
        coordinator._update_state_machine(plugged_in=True, excess_w=5000, production_w=0.0)

        assert coordinator._controller_state == ControllerState.DISABLED

    def test_idle_when_not_plugged_in(
        self, coordinator: TeslaSolarChargerCoordinator
    ):
        """Test state is IDLE when car not plugged in."""
        coordinator._mode = Mode.SOLAR_ONLY
        coordinator._master_enabled = True
        coordinator._update_state_machine(plugged_in=False, excess_w=5000, production_w=0.0)

        assert coordinator._controller_state == ControllerState.IDLE

    def test_tracking_when_solar_available(
        self, coordinator: TeslaSolarChargerCoordinator
    ):
        """Test state is TRACKING when excess solar available."""
        coordinator._mode = Mode.SOLAR_ONLY
        coordinator._master_enabled = True
        coordinator._update_state_machine(plugged_in=True, excess_w=3000, production_w=0.0)

        assert coordinator._controller_state == ControllerState.TRACKING

    def test_forced_when_charge_now(
        self, coordinator: TeslaSolarChargerCoordinator
    ):
        """Test state is FORCED when mode is Charge Now."""
        coordinator._mode = Mode.CHARGE_NOW
        coordinator._master_enabled = True
        coordinator._update_state_machine(plugged_in=True, excess_w=0, production_w=0.0)

        assert coordinator._controller_state == ControllerState.FORCED


class TestHysteresisTimers:
    """Test 6-minute stop and 15-minute restart timers."""

    @pytest.fixture
    def coordinator(
        self, mock_hass: MagicMock, mock_config_entry: ConfigEntry
    ) -> TeslaSolarChargerCoordinator:
        """Create coordinator already in the 'car plugged in' state.

        These tests focus on hysteresis behaviour while plugged in. We mark
        `_was_plugged_in` True so the state machine doesn't treat the first
        `plugged_in=True` call as a plug-event (which would clear timers).
        """
        coord = TeslaSolarChargerCoordinator(mock_hass, mock_config_entry)
        coord._mode = Mode.SOLAR_ONLY
        coord._master_enabled = True
        coord._was_plugged_in = True
        return coord

    def test_enters_stopping_state_when_excess_drops(
        self, coordinator: TeslaSolarChargerCoordinator
    ):
        """Test enters STOPPING when excess drops below threshold."""
        coordinator._controller_state = ControllerState.TRACKING
        coordinator._commanded_amps = 10

        # Excess drops to 0 - should start stop timer
        coordinator._update_state_machine(plugged_in=True, excess_w=0, production_w=0.0)

        assert coordinator._controller_state == ControllerState.STOPPING
        assert coordinator._stop_timer_start is not None

    def test_returns_to_tracking_if_excess_recovers(
        self, coordinator: TeslaSolarChargerCoordinator
    ):
        """Test returns to TRACKING if excess recovers during stop timer."""
        coordinator._controller_state = ControllerState.STOPPING
        coordinator._stop_timer_start = time.monotonic()

        # Excess recovers
        coordinator._update_state_machine(plugged_in=True, excess_w=3000, production_w=0.0)

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

        coordinator._update_state_machine(plugged_in=True, excess_w=0, production_w=0.0)

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
        coordinator._update_state_machine(plugged_in=True, excess_w=5000, production_w=0.0)

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

        coordinator._update_state_machine(plugged_in=True, excess_w=5000, production_w=0.0)

        assert coordinator._controller_state == ControllerState.TRACKING

    def test_charge_now_bypasses_cooldown(
        self, coordinator: TeslaSolarChargerCoordinator
    ):
        """Test Charge Now mode bypasses cooldown timer."""
        coordinator._controller_state = ControllerState.COOLDOWN
        coordinator._cooldown_timer_start = time.monotonic()  # Just started

        coordinator._mode = Mode.CHARGE_NOW
        coordinator._update_state_machine(plugged_in=True, excess_w=0, production_w=0.0)

        assert coordinator._controller_state == ControllerState.FORCED

    def test_mode_setter_cancels_stop_timer(
        self, coordinator: TeslaSolarChargerCoordinator
    ):
        """The mode property setter should clear the stop timer when mode changes."""
        coordinator._controller_state = ControllerState.STOPPING
        coordinator._stop_timer_start = time.monotonic()

        # Use the setter (not direct _mode assignment)
        coordinator.mode = Mode.SOLAR_PLUS_GRID

        assert coordinator._stop_timer_start is None

    def test_mode_setter_no_change_keeps_timer(
        self, coordinator: TeslaSolarChargerCoordinator
    ):
        """Setting the same mode does not reset the stop timer."""
        coordinator._mode = Mode.SOLAR_ONLY
        coordinator._controller_state = ControllerState.STOPPING
        timer_start = time.monotonic()
        coordinator._stop_timer_start = timer_start

        coordinator.mode = Mode.SOLAR_ONLY  # same mode

        assert coordinator._stop_timer_start == timer_start


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
        """Test stops charging when excess drops below min_amps threshold.

        With min_amps=5 and voltage=230, min_charging_w = 1150W.
        production=1000W, consumption=2000W (includes 1150W EV draw at 5A),
        excess = 1000 - (2000 - 1150) - 0 = 150W → below 1150W minimum.
        """
        mock_config_entry.options["min_amps"] = 5
        coordinator._controller_state = ControllerState.TRACKING
        coordinator._commanded_amps = 5
        coordinator._is_charging = True  # EV currently drawing

        def get_state(entity_id: str):
            states = {
                "sensor.solar_production": State(
                    entity_id, "1000", {"unit_of_measurement": "W"}
                ),
                "sensor.home_consumption": State(
                    entity_id, "2000", {"unit_of_measurement": "W"}
                ),
                "sensor.tesla_charging_state": State(
                    entity_id, "Charging", {}
                ),
            }
            return states.get(entity_id)

        mock_hass.states.get = MagicMock(side_effect=get_state)

        data = await coordinator._async_update_data()

        # excess = 1000 - (2000 - 1150) = 150W, well below 1150W min
        assert data["excess_w"] == 150.0
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

    @pytest.mark.asyncio
    async def test_works_with_unavailable_sensors(
        self, coordinator: TeslaSolarChargerCoordinator,
        mock_hass: MagicMock,
        mock_config_entry: ConfigEntry
    ):
        """Test Charge Now works even when production/consumption sensors unavailable."""
        mock_config_entry.options["max_amps"] = 32
        
        def get_state(entity_id: str):
            if entity_id == "sensor.tesla_charging_state":
                return State(entity_id, "Stopped", {})
            # Sensors are unavailable (e.g., at night, or solar inverter offline)
            if entity_id == "sensor.solar_production":
                return State(entity_id, STATE_UNAVAILABLE, {"unit_of_measurement": "W"})
            if entity_id == "sensor.home_consumption":
                return State(entity_id, STATE_UNAVAILABLE, {"unit_of_measurement": "W"})
            return None
        
        mock_hass.states.get = MagicMock(side_effect=get_state)
        
        data = await coordinator._async_update_data()
        
        # CRITICAL: Charge Now must work regardless of sensor availability
        assert data["controller_state"] == ControllerState.FORCED.value
        assert data["target_amps"] == 32
        # Verify commands were sent
        mock_hass.services.async_call.assert_called()

    @pytest.mark.asyncio
    async def test_sends_commands_on_mode_change(
        self, coordinator: TeslaSolarChargerCoordinator,
        mock_hass: MagicMock,
        mock_config_entry: ConfigEntry
    ):
        """Test commands are sent when switching to Charge Now."""
        mock_config_entry.options["max_amps"] = 16
        
        def get_state(entity_id: str):
            if entity_id == "sensor.tesla_charging_state":
                return State(entity_id, "Stopped", {})
            return State(entity_id, "1000", {"unit_of_measurement": "W"})
        
        mock_hass.states.get = MagicMock(side_effect=get_state)
        
        # First call - should send amps and switch commands
        data = await coordinator._async_update_data()
        
        assert data["target_amps"] == 16
        
        # Verify service calls were made
        calls = mock_hass.services.async_call.call_args_list
        # Should have called number.set_value and switch.turn_on
        assert len(calls) >= 2


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
    async def test_holds_amps_when_consumption_unavailable(
        self, coordinator: TeslaSolarChargerCoordinator, mock_hass: MagicMock
    ):
        """Hold commanded amps when consumption sensor becomes unavailable.

        Consumption unavailable disables solar tracking; we hold the previously
        commanded amps rather than dropping to 0. (Production unavailable is
        treated as 0W and still allows tracking.)
        """
        coordinator._commanded_amps = 10
        coordinator._controller_state = ControllerState.TRACKING
        coordinator._was_plugged_in = True

        def get_state(entity_id: str):
            if entity_id == "sensor.solar_production":
                return State(entity_id, "5000", {"unit_of_measurement": "W"})
            if entity_id == "sensor.home_consumption":
                return State(entity_id, STATE_UNAVAILABLE, {"unit_of_measurement": "W"})
            if entity_id == "sensor.tesla_charging_state":
                return State(entity_id, "Charging", {})
            return None

        mock_hass.states.get = MagicMock(side_effect=get_state)

        data = await coordinator._async_update_data()

        # Should hold previously commanded amps, not change
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


class TestIsChargingGating:
    """The back-out estimate must respect _is_charging.

    When the switch is off, the EV draws zero — even if _commanded_amps is
    still set to the last commanded value. Gating prevents the excess
    formula from inflating household-load by a stale EV draw estimate.
    """

    @pytest.fixture
    def coordinator(
        self, mock_hass: MagicMock, mock_config_entry: ConfigEntry
    ) -> TeslaSolarChargerCoordinator:
        coord = TeslaSolarChargerCoordinator(mock_hass, mock_config_entry)
        coord._commanded_amps = 10
        return coord

    def test_excess_uses_zero_charge_when_switch_off(
        self, coordinator: TeslaSolarChargerCoordinator
    ):
        """When switch is off, the back-out current_charge_w is 0."""
        coordinator._is_charging = False
        # production=3000, consumption=1000 (no EV currently drawing)
        # If gating were broken: excess = 3000 - (1000 - 2300) - 0 = 4300 (wrong)
        # Correct: excess = 3000 - (1000 - 0) - 0 = 2000
        result = coordinator._compute_excess_w_with_values(3000.0, 1000.0)
        assert result == 2000.0

    def test_excess_uses_commanded_when_switch_on(
        self, coordinator: TeslaSolarChargerCoordinator
    ):
        """When switch is on, the back-out current_charge_w = voltage * commanded_amps."""
        coordinator._is_charging = True
        # 3000 - (3300 - 2300) - 0 = 2000
        result = coordinator._compute_excess_w_with_values(3000.0, 3300.0)
        assert result == 2000.0


class TestReadBatteryState:
    """Test _read_battery_state helper."""

    @pytest.fixture
    def coordinator(
        self, mock_hass: MagicMock, mock_config_entry: ConfigEntry
    ) -> TeslaSolarChargerCoordinator:
        return TeslaSolarChargerCoordinator(mock_hass, mock_config_entry)

    def test_returns_none_pair_when_unconfigured(
        self, coordinator: TeslaSolarChargerCoordinator
    ):
        """No battery sensors set → (None, None)."""
        # Default fixture has no battery sensors configured
        charge_w, soc = coordinator._read_battery_state()
        assert charge_w is None
        assert soc is None

    def test_reads_when_positive_is_charging(
        self,
        coordinator: TeslaSolarChargerCoordinator,
        mock_hass: MagicMock,
        mock_config_entry: ConfigEntry,
    ):
        """positive_is_charging=True: sensor 1500W → returns +1500W (charging)."""
        mock_config_entry.data["battery_power_sensor"] = "sensor.battery_power"
        mock_config_entry.data["battery_soc_sensor"] = "sensor.battery_soc"
        mock_config_entry.data["battery_power_positive_is_charging"] = True

        def get_state(entity_id: str):
            if entity_id == "sensor.battery_power":
                return State(entity_id, "1500", {"unit_of_measurement": "W"})
            if entity_id == "sensor.battery_soc":
                return State(entity_id, "75", {"unit_of_measurement": "%"})
            return None

        mock_hass.states.get = MagicMock(side_effect=get_state)

        charge_w, soc = coordinator._read_battery_state()
        assert charge_w == 1500.0
        assert soc == 75.0

    def test_normalises_when_positive_is_discharging(
        self,
        coordinator: TeslaSolarChargerCoordinator,
        mock_hass: MagicMock,
        mock_config_entry: ConfigEntry,
    ):
        """positive_is_charging=False: sensor +1500W (discharging) → -1500W after normalise."""
        mock_config_entry.data["battery_power_sensor"] = "sensor.battery_power"
        mock_config_entry.data["battery_soc_sensor"] = "sensor.battery_soc"
        mock_config_entry.data["battery_power_positive_is_charging"] = False

        def get_state(entity_id: str):
            if entity_id == "sensor.battery_power":
                return State(entity_id, "1500", {"unit_of_measurement": "W"})
            if entity_id == "sensor.battery_soc":
                return State(entity_id, "75", {"unit_of_measurement": "%"})
            return None

        mock_hass.states.get = MagicMock(side_effect=get_state)

        charge_w, soc = coordinator._read_battery_state()
        assert charge_w == -1500.0
        assert soc == 75.0

    def test_returns_none_pair_when_power_unavailable(
        self,
        coordinator: TeslaSolarChargerCoordinator,
        mock_hass: MagicMock,
        mock_config_entry: ConfigEntry,
    ):
        """Power sensor unavailable → (None, None) (skip battery awareness this cycle)."""
        mock_config_entry.data["battery_power_sensor"] = "sensor.battery_power"
        mock_config_entry.data["battery_soc_sensor"] = "sensor.battery_soc"
        mock_config_entry.data["battery_power_positive_is_charging"] = True

        def get_state(entity_id: str):
            if entity_id == "sensor.battery_power":
                return State(entity_id, STATE_UNAVAILABLE, {"unit_of_measurement": "W"})
            if entity_id == "sensor.battery_soc":
                return State(entity_id, "75", {"unit_of_measurement": "%"})
            return None

        mock_hass.states.get = MagicMock(side_effect=get_state)

        charge_w, soc = coordinator._read_battery_state()
        assert charge_w is None
        assert soc is None

    def test_returns_none_pair_when_soc_unavailable(
        self,
        coordinator: TeslaSolarChargerCoordinator,
        mock_hass: MagicMock,
        mock_config_entry: ConfigEntry,
    ):
        """SoC sensor unavailable → (None, None)."""
        mock_config_entry.data["battery_power_sensor"] = "sensor.battery_power"
        mock_config_entry.data["battery_soc_sensor"] = "sensor.battery_soc"
        mock_config_entry.data["battery_power_positive_is_charging"] = True

        def get_state(entity_id: str):
            if entity_id == "sensor.battery_power":
                return State(entity_id, "1500", {"unit_of_measurement": "W"})
            if entity_id == "sensor.battery_soc":
                return State(entity_id, STATE_UNKNOWN, {"unit_of_measurement": "%"})
            return None

        mock_hass.states.get = MagicMock(side_effect=get_state)

        charge_w, soc = coordinator._read_battery_state()
        assert charge_w is None
        assert soc is None


class TestApplyBatteryPriorityHardCutoff:
    """Hard-cutoff style: SoC < limit → excess=0; SoC >= limit → unchanged."""

    @pytest.fixture
    def coordinator(
        self, mock_hass: MagicMock, mock_config_entry: ConfigEntry
    ) -> TeslaSolarChargerCoordinator:
        coord = TeslaSolarChargerCoordinator(mock_hass, mock_config_entry)
        mock_config_entry.options["battery_priority_charge_limit_pct"] = 80
        mock_config_entry.options["battery_priority_style"] = "hard_cutoff"
        return coord

    def test_below_limit_zeros_excess(
        self, coordinator: TeslaSolarChargerCoordinator
    ):
        assert coordinator._apply_battery_priority(5000.0, 79.0) == 0.0

    def test_at_limit_passes_through(
        self, coordinator: TeslaSolarChargerCoordinator
    ):
        assert coordinator._apply_battery_priority(5000.0, 80.0) == 5000.0

    def test_above_limit_passes_through(
        self, coordinator: TeslaSolarChargerCoordinator
    ):
        assert coordinator._apply_battery_priority(5000.0, 95.0) == 5000.0

    def test_no_battery_passes_through(
        self, coordinator: TeslaSolarChargerCoordinator
    ):
        assert coordinator._apply_battery_priority(5000.0, None) == 5000.0

    def test_excess_none_passes_through(
        self, coordinator: TeslaSolarChargerCoordinator
    ):
        assert coordinator._apply_battery_priority(None, 50.0) is None


class TestApplyBatteryPriorityGraduated:
    """Graduated style mirrors Olaf's curve, relative to the configured limit.

    Buckets (with limit=L, voltage=230):
      SoC <= L                    → excess = 0  (battery priority)
      L  <  SoC <= L+5            → excess -= 20 * 230 = 4600 W
      L+5 <  SoC <= L+10          → excess -= 15 * 230 = 3450 W
      L+10 < SoC <= L+15          → excess -= 10 * 230 = 2300 W
      L+15 < SoC <= L+19          → excess -=  5 * 230 = 1150 W
      SoC > L+19                  → excess -=  1 * 230 =  230 W
    Result clamped to >= 0.
    """

    @pytest.fixture
    def coordinator(
        self, mock_hass: MagicMock, mock_config_entry: ConfigEntry
    ) -> TeslaSolarChargerCoordinator:
        coord = TeslaSolarChargerCoordinator(mock_hass, mock_config_entry)
        mock_config_entry.options["battery_priority_charge_limit_pct"] = 80
        mock_config_entry.options["battery_priority_style"] = "graduated"
        return coord

    def test_at_or_below_limit_zeros(
        self, coordinator: TeslaSolarChargerCoordinator
    ):
        assert coordinator._apply_battery_priority(10000.0, 80.0) == 0.0
        assert coordinator._apply_battery_priority(10000.0, 50.0) == 0.0

    def test_first_bucket_subtracts_20_amps(
        self, coordinator: TeslaSolarChargerCoordinator
    ):
        # SoC=85 (limit+5) → bucket 1 → -20A * 230V = -4600W
        assert coordinator._apply_battery_priority(10000.0, 85.0) == 10000.0 - 4600.0

    def test_second_bucket_subtracts_15_amps(
        self, coordinator: TeslaSolarChargerCoordinator
    ):
        # SoC=90 (limit+10) → bucket 2 → -15A * 230V = -3450W
        assert coordinator._apply_battery_priority(10000.0, 90.0) == 10000.0 - 3450.0

    def test_third_bucket_subtracts_10_amps(
        self, coordinator: TeslaSolarChargerCoordinator
    ):
        # SoC=95 (limit+15) → bucket 3 → -10A * 230V = -2300W
        assert coordinator._apply_battery_priority(10000.0, 95.0) == 10000.0 - 2300.0

    def test_fourth_bucket_subtracts_5_amps(
        self, coordinator: TeslaSolarChargerCoordinator
    ):
        # SoC=99 (limit+19) → bucket 4 → -5A * 230V = -1150W
        assert coordinator._apply_battery_priority(10000.0, 99.0) == 10000.0 - 1150.0

    def test_fifth_bucket_subtracts_1_amp(
        self, coordinator: TeslaSolarChargerCoordinator
    ):
        # SoC=100 (>limit+19) → bucket 5 → -1A * 230V = -230W
        assert coordinator._apply_battery_priority(10000.0, 100.0) == 10000.0 - 230.0

    def test_clamps_to_zero_when_deduction_exceeds_excess(
        self, coordinator: TeslaSolarChargerCoordinator
    ):
        # SoC=85 → -4600W. excess=2000 → clamped to 0
        assert coordinator._apply_battery_priority(2000.0, 85.0) == 0.0

    def test_relative_buckets_with_lower_limit(
        self,
        coordinator: TeslaSolarChargerCoordinator,
        mock_config_entry: ConfigEntry,
    ):
        """With limit=60, bucket 1 covers 60 < SoC <= 65."""
        mock_config_entry.options["battery_priority_charge_limit_pct"] = 60
        # SoC=65 → first bucket → -4600W
        assert coordinator._apply_battery_priority(10000.0, 65.0) == 10000.0 - 4600.0
        # SoC=60 → at limit → zero
        assert coordinator._apply_battery_priority(10000.0, 60.0) == 0.0


class TestBatteryAwarenessIntegration:
    """End-to-end via _async_update_data with battery sensors configured."""

    @pytest.fixture
    def coordinator(
        self,
        mock_hass: MagicMock,
        mock_config_entry: ConfigEntry,
    ) -> TeslaSolarChargerCoordinator:
        mock_config_entry.data["battery_power_sensor"] = "sensor.battery_power"
        mock_config_entry.data["battery_soc_sensor"] = "sensor.battery_soc"
        mock_config_entry.data["battery_power_positive_is_charging"] = True
        mock_config_entry.options["battery_priority_charge_limit_pct"] = 80
        mock_config_entry.options["battery_priority_style"] = "hard_cutoff"

        coord = TeslaSolarChargerCoordinator(mock_hass, mock_config_entry)
        coord._mode = Mode.SOLAR_ONLY
        coord._master_enabled = True
        coord._was_plugged_in = True
        coord._controller_state = ControllerState.TRACKING
        return coord

    @pytest.mark.asyncio
    async def test_below_limit_with_solar_goes_to_stopping(
        self,
        coordinator: TeslaSolarChargerCoordinator,
        mock_hass: MagicMock,
    ):
        """SoC below limit blocks EV charging even with abundant solar."""
        def get_state(entity_id: str):
            if entity_id == "sensor.solar_production":
                return State(entity_id, "5000", {"unit_of_measurement": "W"})
            if entity_id == "sensor.home_consumption":
                return State(entity_id, "500", {"unit_of_measurement": "W"})
            if entity_id == "sensor.tesla_charging_state":
                return State(entity_id, "Charging", {})
            if entity_id == "sensor.battery_power":
                return State(entity_id, "2000", {"unit_of_measurement": "W"})
            if entity_id == "sensor.battery_soc":
                return State(entity_id, "60", {"unit_of_measurement": "%"})
            return None

        mock_hass.states.get = MagicMock(side_effect=get_state)
        data = await coordinator._async_update_data()

        # Battery priority active → excess gated to 0 → state goes to STOPPING
        assert data["controller_state"] == ControllerState.STOPPING.value
        assert data["battery_priority_active"] is True
        assert data["battery_soc_pct"] == 60.0
        assert data["battery_power_w"] == 2000.0

    @pytest.mark.asyncio
    async def test_above_limit_charges_normally(
        self,
        coordinator: TeslaSolarChargerCoordinator,
        mock_hass: MagicMock,
    ):
        """SoC at/above limit → battery flow ignored, normal tracking."""
        def get_state(entity_id: str):
            if entity_id == "sensor.solar_production":
                return State(entity_id, "5000", {"unit_of_measurement": "W"})
            if entity_id == "sensor.home_consumption":
                return State(entity_id, "500", {"unit_of_measurement": "W"})
            if entity_id == "sensor.tesla_charging_state":
                return State(entity_id, "Charging", {})
            if entity_id == "sensor.battery_power":
                return State(entity_id, "2000", {"unit_of_measurement": "W"})
            if entity_id == "sensor.battery_soc":
                return State(entity_id, "85", {"unit_of_measurement": "%"})
            return None

        mock_hass.states.get = MagicMock(side_effect=get_state)
        data = await coordinator._async_update_data()

        assert data["controller_state"] == ControllerState.TRACKING.value
        assert data["battery_priority_active"] is False
        assert data["target_amps"] > 0

    @pytest.mark.asyncio
    async def test_battery_unavailable_falls_back(
        self,
        coordinator: TeslaSolarChargerCoordinator,
        mock_hass: MagicMock,
    ):
        """Battery sensor unavailable → fall back to no-battery formula (no gating)."""
        def get_state(entity_id: str):
            if entity_id == "sensor.solar_production":
                return State(entity_id, "5000", {"unit_of_measurement": "W"})
            if entity_id == "sensor.home_consumption":
                return State(entity_id, "500", {"unit_of_measurement": "W"})
            if entity_id == "sensor.tesla_charging_state":
                return State(entity_id, "Charging", {})
            if entity_id == "sensor.battery_power":
                return State(entity_id, STATE_UNAVAILABLE, {"unit_of_measurement": "W"})
            if entity_id == "sensor.battery_soc":
                return State(entity_id, "60", {"unit_of_measurement": "%"})
            return None

        mock_hass.states.get = MagicMock(side_effect=get_state)
        data = await coordinator._async_update_data()

        # No gating despite SoC=60 because power sensor is unavailable
        assert data["battery_priority_active"] is False
        assert data["battery_soc_pct"] is None
        assert data["battery_power_w"] is None
        assert data["controller_state"] == ControllerState.TRACKING.value


class TestBuildDataDictBatteryKeys:
    """Data dict exposes battery state keys (None when unconfigured)."""

    @pytest.fixture
    def coordinator(
        self, mock_hass: MagicMock, mock_config_entry: ConfigEntry
    ) -> TeslaSolarChargerCoordinator:
        return TeslaSolarChargerCoordinator(mock_hass, mock_config_entry)

    @pytest.mark.asyncio
    async def test_battery_keys_present_when_unconfigured(
        self, coordinator: TeslaSolarChargerCoordinator,
        mock_hass: MagicMock,
    ):
        """Even with no battery sensors, the data dict includes the keys (None)."""
        coordinator._mode = Mode.OFF
        coordinator._master_enabled = True

        def get_state(entity_id: str):
            if entity_id == "sensor.tesla_charging_state":
                return State(entity_id, "Disconnected", {})
            return State(entity_id, "1000", {"unit_of_measurement": "W"})

        mock_hass.states.get = MagicMock(side_effect=get_state)
        data = await coordinator._async_update_data()

        assert "battery_power_w" in data
        assert "battery_soc_pct" in data
        assert "battery_priority_active" in data
        assert data["battery_power_w"] is None
        assert data["battery_soc_pct"] is None
        assert data["battery_priority_active"] is False


class TestExcessPreBatteryAndDeduction:
    """The data dict exposes the pre-battery excess and the deduction applied
    by battery priority, so users can see the effect of gating at a glance."""

    @pytest.fixture
    def coordinator(
        self,
        mock_hass: MagicMock,
        mock_config_entry: ConfigEntry,
    ) -> TeslaSolarChargerCoordinator:
        mock_config_entry.data["battery_power_sensor"] = "sensor.battery_power"
        mock_config_entry.data["battery_soc_sensor"] = "sensor.battery_soc"
        mock_config_entry.data["battery_power_positive_is_charging"] = True
        mock_config_entry.options["battery_priority_charge_limit_pct"] = 80
        mock_config_entry.options["battery_priority_style"] = "graduated"

        coord = TeslaSolarChargerCoordinator(mock_hass, mock_config_entry)
        coord._mode = Mode.SOLAR_ONLY
        coord._master_enabled = True
        coord._was_plugged_in = True
        coord._controller_state = ControllerState.TRACKING
        return coord

    @pytest.mark.asyncio
    async def test_pre_battery_and_deduction_in_graduated_band(
        self,
        coordinator: TeslaSolarChargerCoordinator,
        mock_hass: MagicMock,
    ):
        """SoC=85 (limit+5) → bucket 1 → 20A * 230V = 4600W deduction."""
        def get_state(entity_id: str):
            if entity_id == "sensor.solar_production":
                return State(entity_id, "10000", {"unit_of_measurement": "W"})
            if entity_id == "sensor.home_consumption":
                return State(entity_id, "0", {"unit_of_measurement": "W"})
            if entity_id == "sensor.tesla_charging_state":
                return State(entity_id, "Charging", {})
            if entity_id == "sensor.battery_power":
                return State(entity_id, "0", {"unit_of_measurement": "W"})
            if entity_id == "sensor.battery_soc":
                return State(entity_id, "85", {"unit_of_measurement": "%"})
            return None

        mock_hass.states.get = MagicMock(side_effect=get_state)
        data = await coordinator._async_update_data()

        # Pre-battery excess = production - consumption = 10000 - 0 = 10000W
        # (no EV draw since _is_charging is False initially)
        assert data["excess_pre_battery_w"] == 10000.0
        # Bucket 1 deduction at SoC=85 with limit=80 → 20A × 230V = 4600W
        assert data["battery_deduction_w"] == 4600.0
        # Final excess = 10000 - 4600 = 5400W
        assert data["excess_w"] == 5400.0

    @pytest.mark.asyncio
    async def test_deduction_zero_above_top_band(
        self,
        coordinator: TeslaSolarChargerCoordinator,
        mock_hass: MagicMock,
    ):
        """SoC=100 (limit+20, beyond top band) → 1A × 230V = 230W deduction."""
        def get_state(entity_id: str):
            if entity_id == "sensor.solar_production":
                return State(entity_id, "5000", {"unit_of_measurement": "W"})
            if entity_id == "sensor.home_consumption":
                return State(entity_id, "0", {"unit_of_measurement": "W"})
            if entity_id == "sensor.tesla_charging_state":
                return State(entity_id, "Charging", {})
            if entity_id == "sensor.battery_power":
                return State(entity_id, "0", {"unit_of_measurement": "W"})
            if entity_id == "sensor.battery_soc":
                return State(entity_id, "100", {"unit_of_measurement": "%"})
            return None

        mock_hass.states.get = MagicMock(side_effect=get_state)
        data = await coordinator._async_update_data()

        assert data["excess_pre_battery_w"] == 5000.0
        assert data["battery_deduction_w"] == 230.0
        assert data["excess_w"] == 4770.0

    @pytest.mark.asyncio
    async def test_deduction_below_limit_zeros_excess(
        self,
        coordinator: TeslaSolarChargerCoordinator,
        mock_hass: MagicMock,
    ):
        """SoC <= limit → all of pre-battery excess is deducted."""
        def get_state(entity_id: str):
            if entity_id == "sensor.solar_production":
                return State(entity_id, "5000", {"unit_of_measurement": "W"})
            if entity_id == "sensor.home_consumption":
                return State(entity_id, "0", {"unit_of_measurement": "W"})
            if entity_id == "sensor.tesla_charging_state":
                return State(entity_id, "Charging", {})
            if entity_id == "sensor.battery_power":
                return State(entity_id, "0", {"unit_of_measurement": "W"})
            if entity_id == "sensor.battery_soc":
                return State(entity_id, "70", {"unit_of_measurement": "%"})
            return None

        mock_hass.states.get = MagicMock(side_effect=get_state)
        data = await coordinator._async_update_data()

        assert data["excess_pre_battery_w"] == 5000.0
        assert data["battery_deduction_w"] == 5000.0
        assert data["excess_w"] == 0.0

    @pytest.mark.asyncio
    async def test_deduction_zero_when_no_battery(
        self,
        mock_hass: MagicMock,
        mock_config_entry: ConfigEntry,
    ):
        """No battery configured → deduction is 0, pre-battery == excess."""
        coord = TeslaSolarChargerCoordinator(mock_hass, mock_config_entry)
        coord._mode = Mode.SOLAR_ONLY
        coord._master_enabled = True
        coord._was_plugged_in = True
        coord._controller_state = ControllerState.TRACKING

        def get_state(entity_id: str):
            if entity_id == "sensor.solar_production":
                return State(entity_id, "5000", {"unit_of_measurement": "W"})
            if entity_id == "sensor.home_consumption":
                return State(entity_id, "1000", {"unit_of_measurement": "W"})
            if entity_id == "sensor.tesla_charging_state":
                return State(entity_id, "Charging", {})
            return None

        mock_hass.states.get = MagicMock(side_effect=get_state)
        data = await coord._async_update_data()

        assert data["excess_pre_battery_w"] == 4000.0
        assert data["battery_deduction_w"] == 0.0
        assert data["excess_w"] == 4000.0


class TestAmpsResetInNonChargingStates:
    """When plugged in but not actively charging, the integration must reset
    the BLE proxy's amps number to 0 — not just rely on the switch being off.

    Bug scenario: integration commands 10A → user unplugs → switch goes off
    via send_switch(off) but commanded amps on the proxy stays at 10 → user
    replugs while integration is in IDLE / COOLDOWN / DISABLED → if anything
    external (Tesla auto-resume, proxy switch toggled elsewhere) starts
    charging, the car draws at the stale 10A because the integration never
    cleared it.

    STOPPING is intentionally exempt: it holds the previous amps so the EV
    keeps charging while we wait out the 6-min stop timer.
    """

    @pytest.fixture
    def coordinator(
        self, mock_hass: MagicMock, mock_config_entry: ConfigEntry
    ) -> TeslaSolarChargerCoordinator:
        coord = TeslaSolarChargerCoordinator(mock_hass, mock_config_entry)
        coord._mode = Mode.SOLAR_ONLY
        coord._master_enabled = True
        coord._was_plugged_in = True
        # Stale value from a previous TRACKING session
        coord._commanded_amps = 10
        return coord

    @staticmethod
    def _amps_set_calls(mock_hass: MagicMock) -> list[int]:
        """Extract every value passed to number.set_value on the amps entity."""
        return [
            c.args[2]["value"]
            for c in mock_hass.services.async_call.call_args_list
            if c.args[0] == "number" and c.args[1] == "set_value"
        ]

    @pytest.mark.asyncio
    async def test_idle_with_plugged_in_sends_amps_zero(
        self, coordinator: TeslaSolarChargerCoordinator, mock_hass: MagicMock
    ):
        coordinator._controller_state = ControllerState.IDLE

        def get_state(entity_id: str):
            states = {
                "sensor.solar_production": State(
                    entity_id, "0", {"unit_of_measurement": "W"}
                ),
                "sensor.home_consumption": State(
                    entity_id, "500", {"unit_of_measurement": "W"}
                ),
                "sensor.tesla_charging_state": State(entity_id, "Stopped", {}),
            }
            return states.get(entity_id)

        mock_hass.states.get = MagicMock(side_effect=get_state)
        await coordinator._async_update_data()

        assert 0 in self._amps_set_calls(mock_hass), (
            "IDLE + plugged_in must reset amps to 0; commanded_amps stale at 10"
        )
        assert coordinator._commanded_amps == 0

    @pytest.mark.asyncio
    async def test_cooldown_with_plugged_in_sends_amps_zero(
        self, coordinator: TeslaSolarChargerCoordinator, mock_hass: MagicMock
    ):
        coordinator._controller_state = ControllerState.COOLDOWN
        coordinator._cooldown_timer_start = time.monotonic()  # just started

        def get_state(entity_id: str):
            states = {
                "sensor.solar_production": State(
                    entity_id, "0", {"unit_of_measurement": "W"}
                ),
                "sensor.home_consumption": State(
                    entity_id, "500", {"unit_of_measurement": "W"}
                ),
                "sensor.tesla_charging_state": State(entity_id, "Stopped", {}),
            }
            return states.get(entity_id)

        mock_hass.states.get = MagicMock(side_effect=get_state)
        await coordinator._async_update_data()

        assert 0 in self._amps_set_calls(mock_hass)

    @pytest.mark.asyncio
    async def test_disabled_with_plugged_in_sends_amps_zero(
        self, coordinator: TeslaSolarChargerCoordinator, mock_hass: MagicMock
    ):
        coordinator._mode = Mode.OFF  # → DISABLED in state machine

        def get_state(entity_id: str):
            states = {
                "sensor.solar_production": State(
                    entity_id, "0", {"unit_of_measurement": "W"}
                ),
                "sensor.home_consumption": State(
                    entity_id, "500", {"unit_of_measurement": "W"}
                ),
                "sensor.tesla_charging_state": State(entity_id, "Stopped", {}),
            }
            return states.get(entity_id)

        mock_hass.states.get = MagicMock(side_effect=get_state)
        await coordinator._async_update_data()

        assert 0 in self._amps_set_calls(mock_hass)

    @pytest.mark.asyncio
    async def test_stopping_with_plugged_in_holds_amps(
        self, coordinator: TeslaSolarChargerCoordinator, mock_hass: MagicMock
    ):
        """STOPPING is the intentional exemption — hold amps while the
        6-min stop timer ticks."""
        coordinator._controller_state = ControllerState.STOPPING
        coordinator._stop_timer_start = time.monotonic()  # just started
        coordinator._is_charging = True

        def get_state(entity_id: str):
            states = {
                "sensor.solar_production": State(
                    entity_id, "0", {"unit_of_measurement": "W"}
                ),
                "sensor.home_consumption": State(
                    entity_id, "3000", {"unit_of_measurement": "W"}
                ),
                "sensor.tesla_charging_state": State(entity_id, "Charging", {}),
            }
            return states.get(entity_id)

        mock_hass.states.get = MagicMock(side_effect=get_state)
        await coordinator._async_update_data()

        # STOPPING must not touch amps
        assert self._amps_set_calls(mock_hass) == []
        # Commanded amps preserved
        assert coordinator._commanded_amps == 10

    @pytest.mark.asyncio
    async def test_idle_with_not_plugged_in_does_not_send_amps(
        self, coordinator: TeslaSolarChargerCoordinator, mock_hass: MagicMock
    ):
        """Not plugged in → leave the proxy alone. No amps update."""
        coordinator._controller_state = ControllerState.IDLE
        coordinator._was_plugged_in = False

        def get_state(entity_id: str):
            states = {
                "sensor.solar_production": State(
                    entity_id, "0", {"unit_of_measurement": "W"}
                ),
                "sensor.home_consumption": State(
                    entity_id, "500", {"unit_of_measurement": "W"}
                ),
                "sensor.tesla_charging_state": State(
                    entity_id, "Disconnected", {}
                ),
            }
            return states.get(entity_id)

        mock_hass.states.get = MagicMock(side_effect=get_state)
        await coordinator._async_update_data()

        # No amps set call should have been made
        assert self._amps_set_calls(mock_hass) == []
        # _commanded_amps preserved (we didn't touch it)
        assert coordinator._commanded_amps == 10

    @pytest.mark.asyncio
    async def test_battery_priority_below_limit_lands_in_cooldown_with_zero_amps(
        self,
        mock_hass: MagicMock,
        mock_config_entry: ConfigEntry,
    ):
        """Battery priority compatibility: when battery gates excess to 0,
        the state machine eventually lands the controller in STOPPING →
        COOLDOWN. In COOLDOWN the new behaviour must apply: amps go to 0.
        STOPPING (the intermediate state) still holds, as before.
        """
        mock_config_entry.data["battery_power_sensor"] = "sensor.battery_power"
        mock_config_entry.data["battery_soc_sensor"] = "sensor.battery_soc"
        mock_config_entry.data["battery_power_positive_is_charging"] = True
        mock_config_entry.options["battery_priority_charge_limit_pct"] = 80
        mock_config_entry.options["battery_priority_style"] = "hard_cutoff"

        coord = TeslaSolarChargerCoordinator(mock_hass, mock_config_entry)
        coord._mode = Mode.SOLAR_ONLY
        coord._master_enabled = True
        coord._was_plugged_in = True
        coord._commanded_amps = 10
        # Pretend we already passed STOPPING and entered COOLDOWN
        coord._controller_state = ControllerState.COOLDOWN
        coord._cooldown_timer_start = time.monotonic()

        def get_state(entity_id: str):
            states = {
                "sensor.solar_production": State(
                    entity_id, "5000", {"unit_of_measurement": "W"}
                ),
                "sensor.home_consumption": State(
                    entity_id, "500", {"unit_of_measurement": "W"}
                ),
                "sensor.tesla_charging_state": State(entity_id, "Stopped", {}),
                "sensor.battery_power": State(
                    entity_id, "2000", {"unit_of_measurement": "W"}
                ),
                "sensor.battery_soc": State(
                    entity_id, "60", {"unit_of_measurement": "%"}
                ),
            }
            return states.get(entity_id)

        mock_hass.states.get = MagicMock(side_effect=get_state)
        data = await coord._async_update_data()

        # Battery still gates excess regardless of fix
        assert data["battery_priority_active"] is True
        # COOLDOWN: amps reset to 0 by the new behaviour
        assert 0 in TestAmpsResetInNonChargingStates._amps_set_calls(mock_hass)

