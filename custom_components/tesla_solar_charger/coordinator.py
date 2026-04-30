"""DataUpdateCoordinator for Tesla Solar Charger."""
from __future__ import annotations

import logging
import time
from datetime import timedelta
from typing import TYPE_CHECKING, Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN, UnitOfPower
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import (
    DEFAULT_MARGIN_W,
    DEFAULT_MAX_AMPS,
    DEFAULT_MIN_AMPS,
    DEFAULT_MIN_SOLAR_GENERATION_W,
    DEFAULT_RESTART_DELAY_SECONDS,
    DEFAULT_STOP_DELAY_SECONDS,
    DEFAULT_UPDATE_INTERVAL_SECONDS,
    DEFAULT_VOLTAGE,
    DOMAIN,
    ControllerState,
    IEC_PLUGGED_IN_STATES,
    Mode,
)

if TYPE_CHECKING:
    pass

_LOGGER = logging.getLogger(__name__)


class TeslaSolarChargerCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Coordinator for Tesla Solar Charger."""

    config_entry: ConfigEntry

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize the coordinator."""
        self.entry = entry
        self.hass = hass
        
        # Get update interval from options or use default
        update_interval = entry.options.get(
            "update_interval_seconds", DEFAULT_UPDATE_INTERVAL_SECONDS
        )

        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=update_interval),
        )

        # Initialize state
        self._mode: Mode = Mode.OFF
        self._master_enabled: bool = True
        self._controller_state: ControllerState = ControllerState.IDLE
        self._commanded_amps: int | None = None
        self._is_charging: bool = False
        self._last_command_sent_at: float | None = None
        self._last_command_succeeded: bool | None = None
        self._stop_timer_start: float | None = None
        self._cooldown_timer_start: float | None = None
        self._was_plugged_in: bool = False
        self._sensor_unavailable_logged: bool = False

    # --- Properties ---

    @property
    def mode(self) -> Mode:
        """Get current mode."""
        return self._mode

    @mode.setter
    def mode(self, value: Mode) -> None:
        """Set mode."""
        if self._mode != value:
            _LOGGER.info("Mode changed from %s to %s", self._mode, value)
            # Cancel stop timer on mode change
            self._stop_timer_start = None
            self._mode = value

    @property
    def master_enabled(self) -> bool:
        """Get master enable state."""
        return self._master_enabled

    @master_enabled.setter
    def master_enabled(self, value: bool) -> None:
        """Set master enable state."""
        if self._master_enabled != value:
            _LOGGER.info("Master enable changed to %s", value)
            self._master_enabled = value

    # --- Helper Methods ---

    def _get_config_value(self, key: str, default: Any) -> Any:
        """Get config value from options or data with fallback to default."""
        return self.entry.options.get(key, self.entry.data.get(key, default))

    def _read_power_w(self, entity_id: str) -> float | None:
        """Read power from a sensor and convert to watts.
        
        Returns None if sensor is unavailable, unknown, or value cannot be parsed.
        """
        state = self.hass.states.get(entity_id)
        if state is None:
            return None
        
        if state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            return None
        
        try:
            value = float(state.state)
        except (ValueError, TypeError):
            return None
        
        # Convert kW to W if necessary
        unit = state.attributes.get("unit_of_measurement", "")
        if unit in (UnitOfPower.KILO_WATT, "kW"):
            value *= 1000
        
        return value

    def _read_plug_state(self) -> bool:
        """Read plug state from IEC 61851 sensor.
        
        Returns True if plugged in, False otherwise.
        Unavailable sensor is treated as not plugged in.
        """
        entity_id = self.entry.data.get("charging_state_sensor")
        if not entity_id:
            return False
        
        state = self.hass.states.get(entity_id)
        if state is None:
            return False
        
        if state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            return False
        
        return state.state in IEC_PLUGGED_IN_STATES

    def _compute_excess_w(self) -> float | None:
        """Compute excess solar power available for charging.
        
        Formula (consumption includes charging - default):
            excess = production - (consumption - current_charge) - margin
        
        Formula (consumption excludes charging):
            excess = production - consumption - margin
        
        Returns None if any required sensor is unavailable.
        """
        # Read production
        production_entity = self.entry.data.get("production_sensor")
        production_w = self._read_power_w(production_entity)
        if production_w is None:
            return None
        
        # Read and sum consumption
        consumption_entities = self.entry.data.get("consumption_sensors", [])
        total_consumption_w = 0.0
        for entity_id in consumption_entities:
            consumption_w = self._read_power_w(entity_id)
            if consumption_w is None:
                return None
            total_consumption_w += consumption_w
        
        return self._compute_excess_w_with_values(production_w, total_consumption_w)

    def _compute_excess_w_with_values(
        self, production_w: float, consumption_w: float | None
    ) -> float | None:
        """Compute excess solar power with pre-read values.

        Args:
            production_w: Solar production in watts (0 if unavailable)
            consumption_w: Home consumption in watts, or None if unavailable

        Returns:
            Excess watts available for charging, or None if consumption unavailable.
        """
        if consumption_w is None:
            return None

        # Get configuration
        margin_w = self._get_config_value("margin_w", DEFAULT_MARGIN_W)
        consumption_excludes_charging = self.entry.data.get(
            "consumption_excludes_charging", False
        )
        voltage = self.entry.data.get("voltage", DEFAULT_VOLTAGE)
        
        # Calculate current charge power
        current_charge_w = 0.0
        if not consumption_excludes_charging and self._commanded_amps:
            current_charge_w = voltage * self._commanded_amps
        
        # Compute excess
        if consumption_excludes_charging:
            excess = production_w - consumption_w - margin_w
        else:
            excess = production_w - (consumption_w - current_charge_w) - margin_w

        return excess

    def _compute_target_amps(self, excess_w: float) -> int:
        """Compute target charging amps from excess watts.
        
        Returns floor(excess_w / voltage), clamped to [0, max_amps].
        Note: min_amps clamping is handled by the state machine.
        """
        if excess_w <= 0:
            return 0
        
        voltage = self.entry.data.get("voltage", DEFAULT_VOLTAGE)
        max_amps = int(self._get_config_value("max_amps", DEFAULT_MAX_AMPS))
        
        target = int(excess_w // voltage)
        return min(target, max_amps)

    def _should_charge_at_minimum(self, production_w: float) -> bool:
        """Check if we should charge at minimum amps (Solar + Grid mode).
        
        Returns True if production is above min_solar_generation threshold.
        """
        min_solar_generation = self._get_config_value(
            "min_solar_generation_w", DEFAULT_MIN_SOLAR_GENERATION_W
        )
        return production_w >= min_solar_generation

    def _update_state_machine(
        self, plugged_in: bool, excess_w: float | None
    ) -> None:
        """Update controller state machine.
        
        Handles transitions between DISABLED, IDLE, TRACKING, STOPPING, 
        COOLDOWN, and FORCED states based on current conditions.
        """
        now = time.monotonic()
        
        # Check for plug state changes (resets timers)
        if plugged_in != self._was_plugged_in:
            _LOGGER.debug("Plug state changed: %s -> %s", self._was_plugged_in, plugged_in)
            self._stop_timer_start = None
            self._cooldown_timer_start = None
            self._was_plugged_in = plugged_in
        
        # Get timing config
        stop_delay = self._get_config_value(
            "stop_delay_seconds", DEFAULT_STOP_DELAY_SECONDS
        )
        restart_delay = self._get_config_value(
            "restart_delay_seconds", DEFAULT_RESTART_DELAY_SECONDS
        )
        min_amps = int(self._get_config_value("min_amps", DEFAULT_MIN_AMPS))
        voltage = self.entry.data.get("voltage", DEFAULT_VOLTAGE)
        min_charging_w = min_amps * voltage
        
        # DISABLED: Mode is Off or master disabled
        if self._mode == Mode.OFF or not self._master_enabled:
            self._controller_state = ControllerState.DISABLED
            self._stop_timer_start = None
            return
        
        # FORCED: Charge Now mode (bypasses all timers)
        if self._mode == Mode.CHARGE_NOW:
            self._controller_state = ControllerState.FORCED
            self._stop_timer_start = None
            self._cooldown_timer_start = None
            return
        
        # IDLE: Not plugged in
        if not plugged_in:
            self._controller_state = ControllerState.IDLE
            self._stop_timer_start = None
            self._cooldown_timer_start = None
            return
        
        # Handle COOLDOWN state
        if self._controller_state == ControllerState.COOLDOWN:
            if self._cooldown_timer_start is not None:
                elapsed = now - self._cooldown_timer_start
                if elapsed < restart_delay:
                    # Still in cooldown
                    return
            # Cooldown expired - can transition to TRACKING
            self._cooldown_timer_start = None
        
        # Check production for Solar + Grid mode minimum threshold
        production_entity = self.entry.data.get("production_sensor")
        production_w = self._read_power_w(production_entity) or 0.0
        
        if self._mode == Mode.SOLAR_PLUS_GRID:
            min_solar_generation = self._get_config_value(
                "min_solar_generation_w", DEFAULT_MIN_SOLAR_GENERATION_W
            )
            if production_w < min_solar_generation:
                # Below minimum solar generation - should stop
                if self._controller_state == ControllerState.TRACKING:
                    self._controller_state = ControllerState.STOPPING
                    self._stop_timer_start = now
                    return
                elif self._controller_state == ControllerState.STOPPING:
                    if self._stop_timer_start and (now - self._stop_timer_start) >= stop_delay:
                        self._controller_state = ControllerState.COOLDOWN
                        self._cooldown_timer_start = now
                    return
                else:
                    self._controller_state = ControllerState.IDLE
                    return
        
        # Determine if excess is sufficient
        excess_sufficient = excess_w is not None and excess_w >= min_charging_w
        
        # Solar + Grid: Continue at minimum if solar present
        if self._mode == Mode.SOLAR_PLUS_GRID:
            min_solar_generation = self._get_config_value(
                "min_solar_generation_w", DEFAULT_MIN_SOLAR_GENERATION_W
            )
            if production_w >= min_solar_generation:
                excess_sufficient = True  # Will charge at minimum
        
        # Handle STOPPING state
        if self._controller_state == ControllerState.STOPPING:
            if excess_sufficient:
                # Excess recovered - return to TRACKING
                self._controller_state = ControllerState.TRACKING
                self._stop_timer_start = None
                return
            
            # Check if stop timer expired
            if self._stop_timer_start is not None:
                elapsed = now - self._stop_timer_start
                if elapsed >= stop_delay:
                    # Timer expired - enter COOLDOWN
                    self._controller_state = ControllerState.COOLDOWN
                    self._cooldown_timer_start = now
                    _LOGGER.info("Charging stopped after %d seconds below threshold", stop_delay)
            return
        
        # Handle TRACKING and other states
        if excess_sufficient or self._controller_state == ControllerState.COOLDOWN:
            if self._controller_state != ControllerState.COOLDOWN:
                self._controller_state = ControllerState.TRACKING
        else:
            # Excess dropped below threshold
            if self._controller_state == ControllerState.TRACKING:
                self._controller_state = ControllerState.STOPPING
                self._stop_timer_start = now
                _LOGGER.debug("Starting stop timer - excess below threshold")
            elif self._controller_state != ControllerState.STOPPING:
                self._controller_state = ControllerState.IDLE

    async def _send_amps(self, amps: int) -> None:
        """Send amps command to ESPHome proxy.
        
        Only sends if value differs from last commanded value.
        Updates commanded_amps on success, logs on failure.
        """
        if self._commanded_amps == amps:
            _LOGGER.debug("Amps unchanged at %d, skipping command", amps)
            return
        
        amps_entity = self.entry.data.get("amps_number")
        if not amps_entity:
            _LOGGER.error("No amps_number entity configured")
            return
        
        _LOGGER.info(
            "Setting charging amps: %d -> %d (entity: %s)",
            self._commanded_amps or 0, amps, amps_entity
        )

        try:
            await self.hass.services.async_call(
                "number",
                "set_value",
                {"entity_id": amps_entity, "value": amps},
                blocking=True,
            )
            self._commanded_amps = amps
            self._last_command_sent_at = time.monotonic()
            self._last_command_succeeded = True
            _LOGGER.info("Successfully set charging amps to %d", amps)
        except Exception as err:
            _LOGGER.error("Failed to set charging amps to %d: %s", amps, err)
            self._last_command_succeeded = False

    async def _send_switch(self, on: bool) -> None:
        """Send switch command to ESPHome proxy.
        
        Only sends if state differs from last known state.
        """
        if self._is_charging == on:
            _LOGGER.debug("Switch already %s, skipping command", "on" if on else "off")
            return
        
        switch_entity = self.entry.data.get("charging_switch")
        if not switch_entity:
            _LOGGER.error("No charging_switch entity configured")
            return
        
        service = "turn_on" if on else "turn_off"
        _LOGGER.info(
            "Turning charging %s (entity: %s)",
            "ON" if on else "OFF", switch_entity
        )

        try:
            await self.hass.services.async_call(
                "switch",
                service,
                {"entity_id": switch_entity},
                blocking=True,
            )
            self._is_charging = on
            self._last_command_sent_at = time.monotonic()
            self._last_command_succeeded = True
            _LOGGER.info("Charging %s", "started" if on else "stopped")
        except Exception as err:
            _LOGGER.error("Failed to %s charging: %s", service, err)
            self._last_command_succeeded = False

    def _compute_seconds_until_transition(self) -> int:
        """Compute seconds until next state transition."""
        now = time.monotonic()
        
        if self._controller_state == ControllerState.STOPPING:
            if self._stop_timer_start is not None:
                stop_delay = self._get_config_value(
                    "stop_delay_seconds", DEFAULT_STOP_DELAY_SECONDS
                )
                elapsed = now - self._stop_timer_start
                remaining = max(0, stop_delay - elapsed)
                return int(remaining)
        
        if self._controller_state == ControllerState.COOLDOWN:
            if self._cooldown_timer_start is not None:
                restart_delay = self._get_config_value(
                    "restart_delay_seconds", DEFAULT_RESTART_DELAY_SECONDS
                )
                elapsed = now - self._cooldown_timer_start
                remaining = max(0, restart_delay - elapsed)
                return int(remaining)
        
        return 0

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch data and execute control loop."""
        _LOGGER.debug(
            "Update cycle starting - Mode: %s, State: %s, Master: %s",
            self._mode.value, self._controller_state.value, self._master_enabled
        )

        # Read sensors
        production_entity = self.entry.data.get("production_sensor")
        production_w_raw = self._read_power_w(production_entity)

        # Treat unavailable production as 0W (no solar - e.g., inverter offline at night)
        if production_w_raw is None:
            production_w = 0.0
            _LOGGER.debug("Production sensor unavailable, treating as 0W")
        else:
            production_w = production_w_raw

        consumption_entities = self.entry.data.get("consumption_sensors", [])
        consumption_w = 0.0
        consumption_valid = True
        for entity_id in consumption_entities:
            val = self._read_power_w(entity_id)
            if val is None:
                consumption_valid = False
                break
            consumption_w += val
        
        if not consumption_valid:
            consumption_w = None
        
        # Read plug state
        plugged_in = self._read_plug_state()
        
        # Compute excess (will use production_w which is 0 if unavailable)
        excess_w = self._compute_excess_w_with_values(production_w, consumption_w)

        # Log sensor unavailability (but don't block execution)
        sensors_available = consumption_w is not None  # Production unavailable is OK (treated as 0)
        if not sensors_available:
            if not self._sensor_unavailable_logged:
                _LOGGER.warning(
                    "Consumption sensor unavailable - Consumption: %s. "
                    "Solar tracking disabled, but Charge Now and Off modes still work.",
                    consumption_w
                )
                self._sensor_unavailable_logged = True
        else:
            self._sensor_unavailable_logged = False
        
        # ALWAYS update state machine - Charge Now and Off modes don't need sensors
        self._update_state_machine(plugged_in, excess_w)
        
        # Compute target amps based on state
        target_amps = 0
        min_amps = int(self._get_config_value("min_amps", DEFAULT_MIN_AMPS))
        max_amps = int(self._get_config_value("max_amps", DEFAULT_MAX_AMPS))
        
        if self._controller_state == ControllerState.FORCED:
            # Charge Now - always charge at max, regardless of sensors
            target_amps = max_amps
            _LOGGER.debug("FORCED mode: target_amps=%d", target_amps)
        elif self._controller_state == ControllerState.TRACKING:
            if sensors_available and excess_w is not None:
                target_amps = self._compute_target_amps(excess_w)
                # Apply minimum in Solar + Grid mode
                if self._mode == Mode.SOLAR_PLUS_GRID and target_amps < min_amps:
                    target_amps = min_amps
                # Clamp to configured range
                if target_amps > 0:
                    target_amps = max(min_amps, min(target_amps, max_amps))
            else:
                # Sensors unavailable during TRACKING - hold current amps
                target_amps = self._commanded_amps or 0
                _LOGGER.debug("TRACKING with unavailable sensors: holding amps=%d", target_amps)
        elif self._controller_state == ControllerState.STOPPING:
            # Hold current amps during stop timer
            target_amps = self._commanded_amps or 0
        
        # Send commands based on state
        if self._controller_state == ControllerState.FORCED:
            # Charge Now - always send commands
            _LOGGER.debug("Sending FORCED commands: amps=%d, switch=on", target_amps)
            await self._send_amps(target_amps)
            await self._send_switch(on=True)
        elif self._controller_state == ControllerState.TRACKING:
            if target_amps > 0:
                await self._send_amps(target_amps)
                await self._send_switch(on=True)
            else:
                await self._send_switch(on=False)
        elif self._controller_state == ControllerState.STOPPING:
            # Hold amps but don't change switch during stop timer
            pass
        elif self._controller_state in (ControllerState.COOLDOWN, ControllerState.IDLE, ControllerState.DISABLED):
            await self._send_switch(on=False)
        
        return self._build_data_dict(
            production_w=production_w,
            consumption_w=consumption_w,
            excess_w=excess_w,
            plugged_in=plugged_in,
            target_amps=target_amps,
        )

    def _build_data_dict(
        self,
        production_w: float | None,
        consumption_w: float | None,
        excess_w: float | None,
        plugged_in: bool,
        target_amps: int | None,
    ) -> dict[str, Any]:
        """Build the data dictionary returned by the coordinator."""
        return {
            "mode": self._mode.value,
            "controller_state": self._controller_state.value,
            "production_w": production_w,
            "consumption_w": consumption_w,
            "excess_w": excess_w,
            "target_amps": target_amps,
            "commanded_amps": self._commanded_amps,
            "is_charging": self._is_charging,
            "plugged_in": plugged_in,
            "seconds_until_next_transition": self._compute_seconds_until_transition(),
            "last_command_sent_at": self._last_command_sent_at,
            "last_command_succeeded": self._last_command_succeeded,
        }
