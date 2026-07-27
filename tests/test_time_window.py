"""Tests for time-window (cheap-rate) charging.

Users on off-peak or free-power tariffs want the car to charge at full rate
between two clock times, ignoring solar entirely. The window is an override
that sits on top of the normal solar-tracking modes.
"""
from __future__ import annotations

import time
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import State

from custom_components.tesla_solar_charger.const import ControllerState, Mode
from custom_components.tesla_solar_charger.coordinator import (
    TeslaSolarChargerCoordinator,
)


def _clock(hhmm: str) -> datetime:
    """A datetime whose .time() is hhmm, for patching dt_util.now()."""
    h, m = (int(x) for x in hhmm.split(":"))
    return datetime(2026, 6, 1, h, m, 0, tzinfo=timezone.utc)


def _patch_now(hhmm: str):
    return patch(
        "custom_components.tesla_solar_charger.coordinator.dt_util.now",
        return_value=_clock(hhmm),
    )


def _night_states(entity_id: str) -> State | None:
    """Plugged in, no sun, house drawing power."""
    states = {
        "sensor.solar_production": State(
            entity_id, "0", {"unit_of_measurement": "W"}
        ),
        "sensor.home_consumption": State(
            entity_id, "800", {"unit_of_measurement": "W"}
        ),
        "sensor.tesla_charging_state": State(entity_id, "Stopped", {}),
    }
    return states.get(entity_id)


class TestTimeWindowActive:
    """Clock-window evaluation, including midnight wrap."""

    @pytest.fixture
    def coordinator(
        self, mock_hass: MagicMock, mock_config_entry: ConfigEntry
    ) -> TeslaSolarChargerCoordinator:
        coord = TeslaSolarChargerCoordinator(mock_hass, mock_config_entry)
        mock_config_entry.options["time_window_enabled"] = True
        mock_config_entry.options["time_window_start"] = "23:00:00"
        mock_config_entry.options["time_window_end"] = "07:00:00"
        return coord

    @pytest.mark.parametrize(
        "hhmm,expected",
        [
            ("23:00", True),   # start inclusive
            ("23:30", True),
            ("02:00", True),   # across midnight
            ("06:59", True),
            ("07:00", False),  # end exclusive
            ("12:00", False),
            ("22:59", False),
        ],
    )
    def test_wrapping_window(
        self, coordinator: TeslaSolarChargerCoordinator, hhmm: str, expected: bool
    ):
        with _patch_now(hhmm):
            assert coordinator._is_time_window_active() is expected

    @pytest.mark.parametrize(
        "hhmm,expected",
        [
            ("09:00", True),
            ("13:00", True),
            ("16:59", True),
            ("17:00", False),
            ("08:59", False),
            ("23:00", False),
        ],
    )
    def test_non_wrapping_window(
        self,
        coordinator: TeslaSolarChargerCoordinator,
        mock_config_entry: ConfigEntry,
        hhmm: str,
        expected: bool,
    ):
        mock_config_entry.options["time_window_start"] = "09:00:00"
        mock_config_entry.options["time_window_end"] = "17:00:00"
        with _patch_now(hhmm):
            assert coordinator._is_time_window_active() is expected

    def test_disabled_is_never_active(
        self, coordinator: TeslaSolarChargerCoordinator, mock_config_entry: ConfigEntry
    ):
        mock_config_entry.options["time_window_enabled"] = False
        with _patch_now("02:00"):
            assert coordinator._is_time_window_active() is False

    def test_zero_length_window_is_inactive(
        self, coordinator: TeslaSolarChargerCoordinator, mock_config_entry: ConfigEntry
    ):
        """start == end is a zero-length window, not a 24h one."""
        mock_config_entry.options["time_window_start"] = "23:00:00"
        mock_config_entry.options["time_window_end"] = "23:00:00"
        with _patch_now("23:00"):
            assert coordinator._is_time_window_active() is False

    def test_unconfigured_is_inactive(
        self, mock_hass: MagicMock, mock_config_entry: ConfigEntry
    ):
        """Defaults (feature never configured) must never charge."""
        coord = TeslaSolarChargerCoordinator(mock_hass, mock_config_entry)
        with _patch_now("02:00"):
            assert coord._is_time_window_active() is False

    def test_enabled_with_unset_times_uses_defaults(
        self, mock_hass: MagicMock, mock_config_entry: ConfigEntry
    ):
        """Enabling without setting times uses the same defaults the entities show."""
        mock_config_entry.options["time_window_enabled"] = True
        mock_config_entry.options.pop("time_window_start", None)
        mock_config_entry.options.pop("time_window_end", None)
        coord = TeslaSolarChargerCoordinator(mock_hass, mock_config_entry)
        with _patch_now("02:00"):
            assert coord._is_time_window_active() is True
        with _patch_now("12:00"):
            assert coord._is_time_window_active() is False

    def test_corrupt_time_fails_closed(
        self, coordinator: TeslaSolarChargerCoordinator, mock_config_entry: ConfigEntry
    ):
        """An unparseable stored value must not silently fall back to the
        default window — that could charge at an hour the user never chose."""
        mock_config_entry.options["time_window_start"] = "not-a-time"
        with _patch_now("02:00"):
            assert coordinator._is_time_window_active() is False


class TestTimeWindowStateMachine:
    """Precedence and behaviour of the TIME_WINDOW override."""

    @pytest.fixture
    def coordinator(
        self, mock_hass: MagicMock, mock_config_entry: ConfigEntry
    ) -> TeslaSolarChargerCoordinator:
        mock_config_entry.options["time_window_enabled"] = True
        mock_config_entry.options["time_window_start"] = "23:00:00"
        mock_config_entry.options["time_window_end"] = "07:00:00"
        mock_config_entry.options["max_amps"] = 32
        coord = TeslaSolarChargerCoordinator(mock_hass, mock_config_entry)
        coord._mode = Mode.SOLAR_ONLY
        coord._master_enabled = True
        coord._was_plugged_in = True
        return coord

    @pytest.mark.asyncio
    async def test_charges_at_max_inside_window(
        self, coordinator: TeslaSolarChargerCoordinator, mock_hass: MagicMock
    ):
        mock_hass.states.get = MagicMock(side_effect=_night_states)
        with _patch_now("02:00"):
            data = await coordinator._async_update_data()

        assert data["controller_state"] == ControllerState.TIME_WINDOW.value
        assert data["target_amps"] == 32
        assert data["time_window_active"] is True

        calls = mock_hass.services.async_call.call_args_list
        assert any(
            c.args[0] == "number" and c.args[2]["value"] == 32 for c in calls
        ), "should command max amps"
        assert any(
            c.args[0] == "switch" and c.args[1] == "turn_on" for c in calls
        ), "should turn charging on"

    @pytest.mark.asyncio
    async def test_outside_window_does_not_force(
        self, coordinator: TeslaSolarChargerCoordinator, mock_hass: MagicMock
    ):
        mock_hass.states.get = MagicMock(side_effect=_night_states)
        with _patch_now("12:00"):
            data = await coordinator._async_update_data()

        assert data["controller_state"] != ControllerState.TIME_WINDOW.value
        assert data["time_window_active"] is False

    @pytest.mark.asyncio
    async def test_mode_off_suppresses_window(
        self, coordinator: TeslaSolarChargerCoordinator, mock_hass: MagicMock
    ):
        coordinator._mode = Mode.OFF
        mock_hass.states.get = MagicMock(side_effect=_night_states)
        with _patch_now("02:00"):
            data = await coordinator._async_update_data()

        assert data["controller_state"] == ControllerState.DISABLED.value

    @pytest.mark.asyncio
    async def test_master_disable_suppresses_window(
        self, coordinator: TeslaSolarChargerCoordinator, mock_hass: MagicMock
    ):
        coordinator._master_enabled = False
        mock_hass.states.get = MagicMock(side_effect=_night_states)
        with _patch_now("02:00"):
            data = await coordinator._async_update_data()

        assert data["controller_state"] == ControllerState.DISABLED.value

    @pytest.mark.asyncio
    async def test_charge_now_wins_over_window(
        self, coordinator: TeslaSolarChargerCoordinator, mock_hass: MagicMock
    ):
        coordinator._mode = Mode.CHARGE_NOW
        mock_hass.states.get = MagicMock(side_effect=_night_states)
        with _patch_now("02:00"):
            data = await coordinator._async_update_data()

        assert data["controller_state"] == ControllerState.FORCED.value

    @pytest.mark.asyncio
    async def test_unplugged_stays_idle(
        self, coordinator: TeslaSolarChargerCoordinator, mock_hass: MagicMock
    ):
        def unplugged(entity_id: str):
            if entity_id == "sensor.tesla_charging_state":
                return State(entity_id, "Disconnected", {})
            return _night_states(entity_id)

        mock_hass.states.get = MagicMock(side_effect=unplugged)
        with _patch_now("02:00"):
            data = await coordinator._async_update_data()

        assert data["controller_state"] == ControllerState.IDLE.value

    @pytest.mark.asyncio
    async def test_window_bypasses_cooldown(
        self, coordinator: TeslaSolarChargerCoordinator, mock_hass: MagicMock
    ):
        """A cooldown lockout must not delay the start of a cheap-rate window."""
        coordinator._controller_state = ControllerState.COOLDOWN
        coordinator._cooldown_timer_start = time.monotonic()
        mock_hass.states.get = MagicMock(side_effect=_night_states)

        with _patch_now("23:00"):
            data = await coordinator._async_update_data()

        assert data["controller_state"] == ControllerState.TIME_WINDOW.value
        assert coordinator._cooldown_timer_start is None

    @pytest.mark.asyncio
    async def test_window_bypasses_in_flight_stop_timer(
        self, coordinator: TeslaSolarChargerCoordinator, mock_hass: MagicMock
    ):
        """A stop timer counting down must be abandoned when the window opens."""
        coordinator._controller_state = ControllerState.STOPPING
        coordinator._stop_timer_start = time.monotonic()
        mock_hass.states.get = MagicMock(side_effect=_night_states)

        with _patch_now("23:00"):
            data = await coordinator._async_update_data()

        assert data["controller_state"] == ControllerState.TIME_WINDOW.value
        assert coordinator._stop_timer_start is None
        assert data["target_amps"] == 32

    @pytest.mark.asyncio
    async def test_mode_off_mid_window_then_close_does_not_replay_exit(
        self, coordinator: TeslaSolarChargerCoordinator, mock_hass: MagicMock
    ):
        """Going Off inside the window, then the window closing, stays DISABLED.

        The window flag is latched every cycle regardless of early returns, so
        a stale 'was in window' must not resurrect solar tracking here.
        """
        mock_hass.states.get = MagicMock(side_effect=_night_states)

        with _patch_now("02:00"):
            assert (
                await coordinator._async_update_data()
            )["controller_state"] == ControllerState.TIME_WINDOW.value

        coordinator._mode = Mode.OFF
        with _patch_now("03:00"):
            off_inside = await coordinator._async_update_data()
        assert off_inside["controller_state"] == ControllerState.DISABLED.value

        with _patch_now("08:00"):
            off_outside = await coordinator._async_update_data()
        assert off_outside["controller_state"] == ControllerState.DISABLED.value
        assert coordinator._was_in_time_window is False

    @pytest.mark.asyncio
    async def test_battery_priority_does_not_block_window(
        self, mock_hass: MagicMock, mock_config_entry: ConfigEntry
    ):
        """Cheap grid power is not solar, so battery priority must not gate it."""
        mock_config_entry.options["time_window_enabled"] = True
        mock_config_entry.options["time_window_start"] = "23:00:00"
        mock_config_entry.options["time_window_end"] = "07:00:00"
        mock_config_entry.options["max_amps"] = 32
        mock_config_entry.data["battery_power_sensor"] = "sensor.battery_power"
        mock_config_entry.data["battery_soc_sensor"] = "sensor.battery_soc"
        mock_config_entry.data["battery_power_positive_is_charging"] = True
        mock_config_entry.options["battery_priority_charge_limit_pct"] = 80

        coord = TeslaSolarChargerCoordinator(mock_hass, mock_config_entry)
        coord._mode = Mode.SOLAR_ONLY
        coord._master_enabled = True
        coord._was_plugged_in = True

        def get_state(entity_id: str):
            if entity_id == "sensor.battery_power":
                return State(entity_id, "0", {"unit_of_measurement": "W"})
            if entity_id == "sensor.battery_soc":
                return State(entity_id, "40", {"unit_of_measurement": "%"})
            return _night_states(entity_id)

        mock_hass.states.get = MagicMock(side_effect=get_state)
        with _patch_now("02:00"):
            data = await coord._async_update_data()

        assert data["controller_state"] == ControllerState.TIME_WINDOW.value
        assert data["target_amps"] == 32


class TestTimeWindowExit:
    """Leaving the window must not pay for 6 minutes of peak-rate charging."""

    @pytest.fixture
    def coordinator(
        self, mock_hass: MagicMock, mock_config_entry: ConfigEntry
    ) -> TeslaSolarChargerCoordinator:
        mock_config_entry.options["time_window_enabled"] = True
        mock_config_entry.options["time_window_start"] = "23:00:00"
        mock_config_entry.options["time_window_end"] = "07:00:00"
        coord = TeslaSolarChargerCoordinator(mock_hass, mock_config_entry)
        coord._mode = Mode.SOLAR_ONLY
        coord._master_enabled = True
        coord._was_plugged_in = True
        return coord

    @pytest.mark.asyncio
    async def test_exit_without_sun_stops_immediately(
        self, coordinator: TeslaSolarChargerCoordinator, mock_hass: MagicMock
    ):
        """No STOPPING, no 6-minute timer - straight to IDLE and switch off.

        Consumption must include the EV draw to be physically consistent: the
        window commands max amps (32 A = 7360 W), so a whole-house meter reads
        800 W of house load plus that, i.e. 8160 W.
        """
        def get_state(entity_id: str):
            states = {
                "sensor.solar_production": State(
                    entity_id, "0", {"unit_of_measurement": "W"}
                ),
                "sensor.home_consumption": State(
                    entity_id, "8160", {"unit_of_measurement": "W"}
                ),
                "sensor.tesla_charging_state": State(entity_id, "Charging", {}),
            }
            return states.get(entity_id)

        mock_hass.states.get = MagicMock(side_effect=get_state)

        with _patch_now("06:59"):
            inside = await coordinator._async_update_data()
        assert inside["controller_state"] == ControllerState.TIME_WINDOW.value

        with _patch_now("07:00"):
            after = await coordinator._async_update_data()

        assert after["controller_state"] == ControllerState.IDLE.value, (
            "must not enter STOPPING and burn 6 minutes at peak rates"
        )
        assert coordinator._stop_timer_start is None
        assert any(
            c.args[0] == "switch" and c.args[1] == "turn_off"
            for c in mock_hass.services.async_call.call_args_list
        )

    @pytest.mark.asyncio
    async def test_exit_with_sun_hands_over_to_tracking(
        self, coordinator: TeslaSolarChargerCoordinator, mock_hass: MagicMock
    ):
        """Plenty of excess at window end - seamless handover, keep charging.

        Consumption includes the EV draw (500 W house + 7360 W at 32 A), so
        real surplus is 6000 - 500 = 5500 W, comfortably above the minimum.
        """
        def get_state(entity_id: str):
            states = {
                "sensor.solar_production": State(
                    entity_id, "6000", {"unit_of_measurement": "W"}
                ),
                "sensor.home_consumption": State(
                    entity_id, "7860", {"unit_of_measurement": "W"}
                ),
                "sensor.tesla_charging_state": State(entity_id, "Charging", {}),
            }
            return states.get(entity_id)

        mock_hass.states.get = MagicMock(side_effect=get_state)

        with _patch_now("06:59"):
            await coordinator._async_update_data()
        with _patch_now("07:00"):
            after = await coordinator._async_update_data()

        assert after["controller_state"] == ControllerState.TRACKING.value
        assert after["target_amps"] > 0


class TestTimeWindowDebugTrace:
    """The per-cycle trace must show whether the window is driving."""

    @pytest.mark.asyncio
    async def test_cycle_trace_reports_window_state(
        self, mock_hass: MagicMock, mock_config_entry: ConfigEntry, caplog
    ):
        import logging

        mock_config_entry.options["time_window_enabled"] = True
        mock_config_entry.options["time_window_start"] = "23:00:00"
        mock_config_entry.options["time_window_end"] = "07:00:00"
        coord = TeslaSolarChargerCoordinator(mock_hass, mock_config_entry)
        coord._mode = Mode.SOLAR_ONLY
        coord._master_enabled = True
        coord._was_plugged_in = True

        mock_hass.states.get = MagicMock(side_effect=_night_states)
        caplog.set_level(
            logging.DEBUG,
            logger="custom_components.tesla_solar_charger.coordinator",
        )

        with _patch_now("02:00"):
            await coord._async_update_data()

        lines = [r.getMessage() for r in caplog.records if "TSC_CYCLE" in r.getMessage()]
        assert lines, "expected a TSC_CYCLE line"
        assert "tw_active=true" in lines[-1]

        transitions = [
            r.getMessage() for r in caplog.records if "TSC_TRANSITION" in r.getMessage()
        ]
        assert any("time_window_open" in t for t in transitions), (
            "transition into the window should record its reason"
        )
