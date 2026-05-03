"""Fixtures for Tesla Solar Charger tests."""
from __future__ import annotations

from collections.abc import Generator
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from homeassistant.const import UnitOfPower
from homeassistant.core import HomeAssistant, State
from homeassistant.config_entries import ConfigEntry

from custom_components.tesla_solar_charger.const import DOMAIN


@pytest.fixture(autouse=True)
def _bypass_frame_helper() -> Generator[None, None, None]:
    """Bypass HA's frame helper for unit tests using MagicMock(spec=HomeAssistant).

    DataUpdateCoordinator.__init__ calls frame.report_usage(), which requires
    the frame helper to be initialized — something only the real `hass`
    fixture sets up. We don't need that telemetry in pure unit tests.
    """
    with patch("homeassistant.helpers.frame.report_usage"):
        yield


@pytest.fixture
def mock_config_entry() -> ConfigEntry:
    """Create a mock config entry."""
    entry = MagicMock(spec=ConfigEntry)
    entry.entry_id = "test_entry_id"
    entry.domain = DOMAIN
    entry.title = "Tesla Solar Charger"
    entry.data = {
        "name": "Tesla Solar Charger",
        "production_sensor": "sensor.solar_production",
        "consumption_sensors": ["sensor.home_consumption"],
        "consumption_excludes_charging": False,
        "amps_number": "number.tesla_charging_amps",
        "charging_switch": "switch.tesla_charging",
        "charging_state_sensor": "sensor.tesla_charging_state",
        "voltage": 230,
    }
    entry.options = {
        "update_interval_seconds": 30,
        "min_amps": 5,
        "max_amps": 32,
        "margin_w": 0,
        "min_solar_generation_w": 200,
        "stop_delay_seconds": 360,
        "restart_delay_seconds": 900,
    }
    entry.runtime_data = None
    return entry


@pytest.fixture
def mock_hass() -> MagicMock:
    """Create a mock Home Assistant instance."""
    hass = MagicMock(spec=HomeAssistant)
    hass.states = MagicMock()
    hass.services = MagicMock()
    hass.config_entries = MagicMock()

    # Default state returns
    def get_state(entity_id: str) -> State | None:
        states = {
            "sensor.solar_production": State(
                "sensor.solar_production", "3000",
                {"unit_of_measurement": UnitOfPower.WATT}
            ),
            "sensor.home_consumption": State(
                "sensor.home_consumption", "1500",
                {"unit_of_measurement": UnitOfPower.WATT}
            ),
            "sensor.tesla_charging_state": State(
                "sensor.tesla_charging_state", "Disconnected", {}
            ),
            "number.tesla_charging_amps": State(
                "number.tesla_charging_amps", "0", {}
            ),
            "switch.tesla_charging": State(
                "switch.tesla_charging", "off", {}
            ),
        }
        return states.get(entity_id)

    hass.states.get = MagicMock(side_effect=get_state)
    hass.services.async_call = AsyncMock()

    return hass



