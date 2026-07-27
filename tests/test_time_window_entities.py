"""Entity tests for time-window charging controls."""
from __future__ import annotations

from datetime import time as dt_time
from unittest.mock import AsyncMock, MagicMock

import pytest

from homeassistant.config_entries import ConfigEntry


class TestTimeWindowTimeEntities:
    """Start/end are TimeEntity controls writing to entry.options."""

    @pytest.mark.asyncio
    async def test_start_time_value(self, mock_hass: MagicMock):
        from custom_components.tesla_solar_charger.time import (
            TeslaSolarChargerChargeWindowStartTime,
        )

        coordinator = MagicMock()
        coordinator.data = {}
        entry = MagicMock()
        entry.entry_id = "test"
        entry.options = {"time_window_start": "23:30:00"}

        ent = TeslaSolarChargerChargeWindowStartTime(coordinator, entry)
        assert ent.native_value == dt_time(23, 30)

    @pytest.mark.asyncio
    async def test_end_time_value(self, mock_hass: MagicMock):
        from custom_components.tesla_solar_charger.time import (
            TeslaSolarChargerChargeWindowEndTime,
        )

        coordinator = MagicMock()
        coordinator.data = {}
        entry = MagicMock()
        entry.entry_id = "test"
        entry.options = {"time_window_end": "07:15:00"}

        ent = TeslaSolarChargerChargeWindowEndTime(coordinator, entry)
        assert ent.native_value == dt_time(7, 15)

    @pytest.mark.asyncio
    async def test_set_value_persists_to_options(
        self, mock_hass: MagicMock, mock_config_entry: ConfigEntry
    ):
        from custom_components.tesla_solar_charger.time import (
            TeslaSolarChargerChargeWindowStartTime,
        )

        coordinator = MagicMock()
        coordinator.data = {}
        coordinator.async_request_refresh = AsyncMock()
        mock_config_entry.options = {}

        ent = TeslaSolarChargerChargeWindowStartTime(coordinator, mock_config_entry)
        ent.hass = mock_hass
        await ent.async_set_value(dt_time(1, 5))

        saved = mock_hass.config_entries.async_update_entry.call_args.kwargs["options"]
        assert saved["time_window_start"] == "01:05:00"
        coordinator.async_request_refresh.assert_called_once()


class TestTimeWindowEnableSwitch:
    """Enabling the feature is a persisted switch, not in-memory state."""

    @pytest.mark.asyncio
    async def test_is_on_reflects_options(self, mock_hass: MagicMock):
        from custom_components.tesla_solar_charger.switch import (
            TeslaSolarChargerTimeWindowSwitch,
        )

        coordinator = MagicMock()
        coordinator.data = {}
        entry = MagicMock()
        entry.entry_id = "test"
        entry.options = {"time_window_enabled": True}

        sw = TeslaSolarChargerTimeWindowSwitch(coordinator, entry)
        assert sw.is_on is True

    @pytest.mark.asyncio
    async def test_defaults_off(self, mock_hass: MagicMock):
        from custom_components.tesla_solar_charger.switch import (
            TeslaSolarChargerTimeWindowSwitch,
        )

        coordinator = MagicMock()
        coordinator.data = {}
        entry = MagicMock()
        entry.entry_id = "test"
        entry.options = {}

        sw = TeslaSolarChargerTimeWindowSwitch(coordinator, entry)
        assert sw.is_on is False

    @pytest.mark.asyncio
    async def test_turn_on_persists(
        self, mock_hass: MagicMock, mock_config_entry: ConfigEntry
    ):
        from custom_components.tesla_solar_charger.switch import (
            TeslaSolarChargerTimeWindowSwitch,
        )

        coordinator = MagicMock()
        coordinator.data = {}
        coordinator.async_request_refresh = AsyncMock()
        mock_config_entry.options = {}

        sw = TeslaSolarChargerTimeWindowSwitch(coordinator, mock_config_entry)
        sw.hass = mock_hass
        await sw.async_turn_on()

        saved = mock_hass.config_entries.async_update_entry.call_args.kwargs["options"]
        assert saved["time_window_enabled"] is True


class TestTimeWindowBinarySensor:
    """Diagnostic visibility of whether the window is currently active."""

    @pytest.mark.asyncio
    async def test_reflects_coordinator_data(self, mock_hass: MagicMock):
        from custom_components.tesla_solar_charger.binary_sensor import (
            TeslaSolarChargerTimeWindowBinarySensor,
        )

        coordinator = MagicMock()
        coordinator.data = {"time_window_active": True}
        entry = MagicMock()
        entry.entry_id = "test"

        sensor = TeslaSolarChargerTimeWindowBinarySensor(coordinator, entry)
        assert sensor.is_on is True

        coordinator.data = {"time_window_active": False}
        assert sensor.is_on is False
