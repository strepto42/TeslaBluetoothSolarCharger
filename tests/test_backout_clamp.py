"""The EV-draw back-out must never exceed measured consumption.

`current_charge_w` is reconstructed from the *commanded* amps, which can be
stale or ahead of what the car is really drawing (a fresh plug-in, a taper, a
lagging power meter). If the reconstruction exceeds the total consumption
reading, backing it out manufactures excess out of nothing and the controller
starts charging when there is no surplus at all.

Physical invariant: when the consumption sensor includes the EV, the EV cannot
be drawing more than the whole-house reading.
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import State

from custom_components.tesla_solar_charger.const import ControllerState, Mode
from custom_components.tesla_solar_charger.coordinator import (
    TeslaSolarChargerCoordinator,
)


class TestBackOutClamp:
    """Unit-level: the back-out is bounded by consumption."""

    @pytest.fixture
    def coordinator(
        self, mock_hass: MagicMock, mock_config_entry: ConfigEntry
    ) -> TeslaSolarChargerCoordinator:
        return TeslaSolarChargerCoordinator(mock_hass, mock_config_entry)

    def test_stale_commanded_amps_cannot_manufacture_excess(
        self, coordinator: TeslaSolarChargerCoordinator
    ):
        """16 A stale command vs a 500 W house reading must not yield surplus."""
        coordinator._commanded_amps = 16   # stale from a previous session
        coordinator._is_charging = True    # transient IEC "Charging" on plug-in

        # Unclamped this would be 0 - (500 - 3680) = +3180 W of phantom excess.
        result = coordinator._compute_excess_w_with_values(0.0, 500.0)

        assert result is not None
        assert result <= 0.0, f"phantom excess manufactured: {result} W"

    def test_healthy_charging_backout_is_unchanged(
        self, coordinator: TeslaSolarChargerCoordinator
    ):
        """When the meter really does include the EV draw, nothing changes."""
        coordinator._commanded_amps = 16
        coordinator._is_charging = True
        # 500 W house + 3680 W EV = 4180 W total
        result = coordinator._compute_excess_w_with_values(5000.0, 4180.0)
        # 5000 - (4180 - 3680) = 4500
        assert result == 4500.0

    def test_taper_is_bounded_not_inflated(
        self, coordinator: TeslaSolarChargerCoordinator
    ):
        """Car tapering below the commanded rate must not inflate excess."""
        coordinator._commanded_amps = 32   # commanded 7360 W
        coordinator._is_charging = True
        # Car actually draws 1150 W; house 500 W; meter reads 1650 W
        result = coordinator._compute_excess_w_with_values(0.0, 1650.0)
        assert result is not None
        assert result <= 0.0, f"taper inflated excess to {result} W"

    def test_negative_consumption_does_not_invert_backout(
        self, coordinator: TeslaSolarChargerCoordinator
    ):
        """A net/export-style sensor reading below zero must not add draw."""
        coordinator._commanded_amps = 16
        coordinator._is_charging = True
        result = coordinator._compute_excess_w_with_values(0.0, -200.0)
        # Back-out clamps to 0, so excess is just 0 - (-200) = 200 at most.
        assert result is not None
        assert result <= 200.0


class TestPlugInAfterDarkNoBurst:
    """Integration-level: plugging in after dark must not start charging."""

    @pytest.mark.asyncio
    async def test_no_charge_burst_on_plug_in_after_dark(
        self, mock_hass: MagicMock, mock_config_entry: ConfigEntry
    ):
        coord = TeslaSolarChargerCoordinator(mock_hass, mock_config_entry)
        coord._mode = Mode.SOLAR_ONLY
        coord._master_enabled = True
        coord._controller_state = ControllerState.IDLE
        coord._was_plugged_in = False
        coord._commanded_amps = 16  # stale from the last daylight session

        def get_state(entity_id: str):
            states = {
                # After dark
                "sensor.solar_production": State(
                    entity_id, "0", {"unit_of_measurement": "W"}
                ),
                # House only - the car is not drawing yet
                "sensor.home_consumption": State(
                    entity_id, "500", {"unit_of_measurement": "W"}
                ),
                # Transient handshake state on plug-in
                "sensor.tesla_charging_state": State(entity_id, "Charging", {}),
            }
            return states.get(entity_id)

        mock_hass.states.get = MagicMock(side_effect=get_state)
        data = await coord._async_update_data()

        assert data["controller_state"] != ControllerState.TRACKING.value, (
            "started tracking on phantom excess after dark"
        )
        assert data["target_amps"] == 0
        assert not any(
            c.args[0] == "switch" and c.args[1] == "turn_on"
            for c in mock_hass.services.async_call.call_args_list
        ), "commanded charging on with no solar"
