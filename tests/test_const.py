"""Tests for const.py - Phase 1."""
from __future__ import annotations

import pytest

from custom_components.tesla_solar_charger.const import (
    DOMAIN,
    PLATFORMS,
    DEFAULT_NAME,
    DEFAULT_VOLTAGE,
    DEFAULT_UPDATE_INTERVAL_SECONDS,
    DEFAULT_MIN_AMPS,
    DEFAULT_MAX_AMPS,
    DEFAULT_MARGIN_W,
    DEFAULT_MIN_SOLAR_GENERATION_W,
    DEFAULT_STOP_DELAY_SECONDS,
    DEFAULT_RESTART_DELAY_SECONDS,
    VOLTAGE_MIN,
    VOLTAGE_MAX,
    AMPS_MIN_LIMIT,
    AMPS_MAX_LIMIT,
    Mode,
    ControllerState,
    IEC_PLUGGED_IN_STATES,
)


class TestDomain:
    """Test domain constant."""

    def test_domain_value(self):
        """Test domain is correct."""
        assert DOMAIN == "tesla_solar_charger"


class TestPlatforms:
    """Test platform configuration."""

    def test_platforms_list(self):
        """Test all required platforms are defined."""
        assert "select" in PLATFORMS
        assert "number" in PLATFORMS
        assert "switch" in PLATFORMS
        assert "sensor" in PLATFORMS
        assert "binary_sensor" in PLATFORMS
        assert len(PLATFORMS) == 5


class TestDefaults:
    """Test default values."""

    def test_default_name(self):
        """Test default name."""
        assert DEFAULT_NAME == "Tesla Solar Charger"

    def test_default_voltage(self):
        """Test default voltage is 230V (EU standard)."""
        assert DEFAULT_VOLTAGE == 230

    def test_default_update_interval(self):
        """Test default update interval is 5 seconds."""
        assert DEFAULT_UPDATE_INTERVAL_SECONDS == 5

    def test_default_min_amps(self):
        """Test default min amps is 5A (Tesla single-phase minimum)."""
        assert DEFAULT_MIN_AMPS == 5

    def test_default_max_amps(self):
        """Test default max amps is 32A."""
        assert DEFAULT_MAX_AMPS == 32

    def test_default_margin(self):
        """Test default margin is 0W."""
        assert DEFAULT_MARGIN_W == 0

    def test_default_min_solar_generation(self):
        """Test default min solar generation is 200W."""
        assert DEFAULT_MIN_SOLAR_GENERATION_W == 200

    def test_default_stop_delay(self):
        """Test default stop delay is 6 minutes (360 seconds)."""
        assert DEFAULT_STOP_DELAY_SECONDS == 360

    def test_default_restart_delay(self):
        """Test default restart delay is 15 minutes (900 seconds)."""
        assert DEFAULT_RESTART_DELAY_SECONDS == 900


class TestLimits:
    """Test limit constants."""

    def test_voltage_range(self):
        """Test voltage range is 100-260V."""
        assert VOLTAGE_MIN == 100
        assert VOLTAGE_MAX == 260

    def test_amps_limits(self):
        """Test amps limits."""
        assert AMPS_MIN_LIMIT == 1
        assert AMPS_MAX_LIMIT == 32


class TestModeEnum:
    """Test Mode enum."""

    def test_mode_values(self):
        """Test all mode values are present."""
        assert Mode.OFF == "Off"
        assert Mode.SOLAR_ONLY == "Solar Only"
        assert Mode.SOLAR_PLUS_GRID == "Solar + Grid"
        assert Mode.CHARGE_NOW == "Charge Now"

    def test_mode_count(self):
        """Test exactly 4 modes exist."""
        assert len(Mode) == 4


class TestControllerStateEnum:
    """Test ControllerState enum."""

    def test_state_values(self):
        """Test all state values are present per CLAUDE.md spec."""
        assert ControllerState.DISABLED == "disabled"
        assert ControllerState.IDLE == "idle"
        assert ControllerState.TRACKING == "tracking"
        assert ControllerState.STOPPING == "stopping"
        assert ControllerState.COOLDOWN == "cooldown"
        assert ControllerState.FORCED == "forced"

    def test_state_count(self):
        """Test exactly 6 states exist."""
        assert len(ControllerState) == 6


class TestIECStates:
    """Test IEC 61851 plugged-in states."""

    def test_plugged_in_states(self):
        """Test plugged-in states match ESPHome proxy values."""
        # From CLAUDE.md: Complete, Stopped, Starting, Charging, Calibrating
        assert "Complete" in IEC_PLUGGED_IN_STATES
        assert "Stopped" in IEC_PLUGGED_IN_STATES
        assert "Starting" in IEC_PLUGGED_IN_STATES
        assert "Charging" in IEC_PLUGGED_IN_STATES
        assert "Calibrating" in IEC_PLUGGED_IN_STATES

    def test_not_plugged_in_states(self):
        """Test states that should NOT be considered plugged in."""
        assert "Disconnected" not in IEC_PLUGGED_IN_STATES
        assert "NoPower" not in IEC_PLUGGED_IN_STATES
        assert "Unknown" not in IEC_PLUGGED_IN_STATES

