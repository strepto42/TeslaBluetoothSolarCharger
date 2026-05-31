"""DataUpdateCoordinator for Tesla Solar Charger."""
from __future__ import annotations

import logging
import time
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN, UnitOfPower
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import (
    BATTERY_GRADUATED_BUCKETS_A,
    BATTERY_GRADUATED_TOP_DEDUCTION_A,
    BATTERY_PRIORITY_STYLE_GRADUATED,
    BATTERY_PRIORITY_STYLE_HARD_CUTOFF,
    DEFAULT_BATTERY_PRIORITY_CHARGE_LIMIT_PCT,
    DEFAULT_BATTERY_PRIORITY_STYLE,
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
    IEC_CHARGING_STATE,
    IEC_PLUGGED_IN_STATES,
    Mode,
    SWITCH_RESEND_INTERVAL_SECONDS,
)

_LOGGER = logging.getLogger(__name__)


class TeslaSolarChargerCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Coordinator for Tesla Solar Charger."""

    config_entry: ConfigEntry

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize the coordinator."""
        self.entry = entry

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
        self._mode: Mode = Mode.SOLAR_ONLY
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
        # Switch re-send throttle: the last on/off value we commanded and when,
        # so we can re-assert a dropped command without flooding the BLE link.
        self._last_switch_desired: bool | None = None
        self._last_switch_sent_at: float | None = None

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

    def _read_charging_active(self) -> bool | None:
        """Read whether the car is *actually* charging, from the IEC sensor.

        Returns True if the car reports it is drawing charge, False if it is
        plugged but not charging, and None if the sensor is missing/unavailable
        (i.e. we cannot tell — typically BLE is down).

        This is the source of truth for whether charging is happening, used in
        preference to our own optimistic record of the last command we sent
        (which may have been dropped over the unreliable BLE link).
        """
        entity_id = self.entry.data.get("charging_state_sensor")
        if not entity_id:
            return None

        state = self.hass.states.get(entity_id)
        if state is None or state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            return None

        return state.state == IEC_CHARGING_STATE

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
        
        # Calculate current charge power. Gated on _is_charging so the
        # back-out doesn't inflate household-load with a stale commanded
        # amps value when the switch is actually off.
        current_charge_w = 0.0
        if (
            not consumption_excludes_charging
            and self._commanded_amps is not None
            and self._is_charging
        ):
            current_charge_w = voltage * self._commanded_amps
        
        # Compute excess
        if consumption_excludes_charging:
            excess = production_w - consumption_w - margin_w
        else:
            excess = production_w - (consumption_w - current_charge_w) - margin_w

        return excess

    def _read_battery_state(self) -> tuple[float | None, float | None]:
        """Read home battery power and SoC.

        Returns (charge_w, soc_pct), where charge_w is normalised so a
        positive value means the battery is *charging* (absorbing power),
        regardless of which sign convention the user's sensor uses.

        Returns (None, None) if either sensor is unconfigured, unavailable,
        or unparseable. Battery awareness is then skipped this cycle.
        """
        power_entity = self.entry.data.get("battery_power_sensor")
        soc_entity = self.entry.data.get("battery_soc_sensor")
        if not power_entity or not soc_entity:
            return None, None

        charge_w = self._read_power_w(power_entity)
        if charge_w is None:
            return None, None

        soc_state = self.hass.states.get(soc_entity)
        if soc_state is None or soc_state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            return None, None
        try:
            soc_pct = float(soc_state.state)
        except (ValueError, TypeError):
            return None, None

        positive_is_charging = self.entry.data.get(
            "battery_power_positive_is_charging", True
        )
        if not positive_is_charging:
            charge_w = -charge_w

        return charge_w, soc_pct

    def _apply_battery_priority(
        self, excess_w: float | None, soc_pct: float | None
    ) -> float | None:
        """Apply home-battery priority gating to the raw excess.

        Mirrors ChargeHQ's published behaviour. With style=hard_cutoff:
        SoC < limit zeros excess (battery has priority); SoC >= limit
        passes excess through unchanged.

        With style=graduated, deductions in 5% SoC bands above the limit
        taper from -20A down to -1A (curve borrowed from a known-good
        local Home Assistant automation).

        If excess_w or soc_pct is None, returns excess_w unchanged.
        """
        if excess_w is None or soc_pct is None:
            return excess_w

        limit = float(
            self._get_config_value(
                "battery_priority_charge_limit_pct",
                DEFAULT_BATTERY_PRIORITY_CHARGE_LIMIT_PCT,
            )
        )
        style = self._get_config_value(
            "battery_priority_style", DEFAULT_BATTERY_PRIORITY_STYLE
        )

        if style == BATTERY_PRIORITY_STYLE_HARD_CUTOFF:
            # ChargeHQ: "Once the limit is reached, all excess solar will
            # be used for EV charging." → strict less-than.
            return 0.0 if soc_pct < limit else excess_w

        # Graduated: at or below the limit, battery has full priority.
        if soc_pct <= limit:
            return 0.0

        # Pick the bucket whose upper bound covers (soc - limit).
        offset = soc_pct - limit
        deduction_a = BATTERY_GRADUATED_TOP_DEDUCTION_A
        for upper_offset, bucket_a in BATTERY_GRADUATED_BUCKETS_A:
            if offset <= upper_offset:
                deduction_a = bucket_a
                break

        voltage = self.entry.data.get("voltage", DEFAULT_VOLTAGE)
        return max(0.0, excess_w - deduction_a * voltage)

    def _compute_target_amps(self, excess_w: float) -> int:
        """Compute target charging amps from excess watts.

        Returns floor(excess_w / voltage), clamped to [min_amps, max_amps].
        Zero/negative excess returns 0 to signal "stop charging" rather than
        clamping up to min_amps.
        """
        if excess_w <= 0:
            return 0

        voltage = self.entry.data.get("voltage", DEFAULT_VOLTAGE)
        min_amps = int(self._get_config_value("min_amps", DEFAULT_MIN_AMPS))
        max_amps = int(self._get_config_value("max_amps", DEFAULT_MAX_AMPS))

        target = int(excess_w // voltage)
        return max(min_amps, min(target, max_amps))

    def _update_state_machine(
        self,
        plugged_in: bool,
        excess_w: float | None,
        production_w: float,
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
            # Cooldown timer expired - transition based on conditions
            self._cooldown_timer_start = None
            # Determine next state after cooldown
            excess_sufficient = excess_w is not None and excess_w >= min_charging_w
            if excess_sufficient:
                self._controller_state = ControllerState.TRACKING
            else:
                self._controller_state = ControllerState.IDLE
            return

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
        """Drive the charging switch toward the desired state.

        Reconciles against the car's *actual* charging state (`self._is_charging`,
        refreshed from the IEC sensor each cycle) rather than trusting that our
        last command landed. While the car's reported state already matches what
        we want, we send nothing (so steady state never floods the BLE link).

        While it disagrees — e.g. we asked for off but a dropped BLE command
        left the car still charging — we re-assert the command, but no more
        often than SWITCH_RESEND_INTERVAL_SECONDS for the *same* desired value.
        A genuine change of desired value is sent immediately.
        """
        now = time.monotonic()

        if self._is_charging == on:
            # Reality already matches intent — nothing to do.
            return

        # Reality disagrees. Throttle re-asserts of the same desired value so
        # BLE latency / a stubborn car can't make us hammer the link.
        if (
            self._last_switch_desired == on
            and self._last_switch_sent_at is not None
            and (now - self._last_switch_sent_at) < SWITCH_RESEND_INTERVAL_SECONDS
        ):
            _LOGGER.debug(
                "Switch %s already commanded %.0fs ago; awaiting effect",
                "on" if on else "off",
                now - self._last_switch_sent_at,
            )
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

        # Record the attempt up front so the throttle applies whether or not
        # the call raises. We do NOT optimistically set _is_charging here — it
        # is refreshed from the IEC sensor at the top of each cycle, so the
        # next cycle re-evaluates against reality and re-sends if needed.
        self._last_switch_desired = on
        self._last_switch_sent_at = now

        try:
            await self.hass.services.async_call(
                "switch",
                service,
                {"entity_id": switch_entity},
                blocking=True,
            )
            self._last_command_sent_at = now
            self._last_command_succeeded = True
            _LOGGER.info("Charging %s commanded", "start" if on else "stop")
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

        # Refresh our notion of whether the car is actually charging from the
        # IEC sensor — the source of truth — rather than trusting that the last
        # switch command we issued actually landed over BLE. When the sensor is
        # unavailable (None) we keep the last known value as a best effort.
        observed_charging = self._read_charging_active()
        if observed_charging is not None:
            self._is_charging = observed_charging

        # Read home battery state (None pair if unconfigured/unavailable)
        battery_power_w, battery_soc_pct = self._read_battery_state()

        # Compute excess (will use production_w which is 0 if unavailable),
        # then apply battery-priority gating if a battery is configured.
        excess_w = self._compute_excess_w_with_values(production_w, consumption_w)
        excess_w_pre_battery = excess_w
        excess_w = self._apply_battery_priority(excess_w, battery_soc_pct)
        battery_priority_active = (
            battery_soc_pct is not None
            and excess_w_pre_battery is not None
            and excess_w != excess_w_pre_battery
        )
        if excess_w_pre_battery is not None and excess_w is not None:
            battery_deduction_w = max(0.0, excess_w_pre_battery - excess_w)
        else:
            battery_deduction_w = 0.0

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
        self._update_state_machine(plugged_in, excess_w, production_w)

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
                if self._mode == Mode.SOLAR_PLUS_GRID:
                    # Floor at min_amps regardless of how low excess is, since
                    # the grid will supplement.
                    target_amps = max(min_amps, self._compute_target_amps(excess_w))
                else:
                    target_amps = self._compute_target_amps(excess_w)
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
                if plugged_in:
                    await self._send_amps(0)
                await self._send_switch(on=False)
        elif self._controller_state == ControllerState.STOPPING:
            # Hold amps but don't change switch during stop timer
            pass
        elif self._controller_state in (ControllerState.COOLDOWN, ControllerState.IDLE, ControllerState.DISABLED):
            # Belt-and-braces: while plugged in, zero out the proxy's amps
            # number so a stale value can't be drawn upon if anything
            # external (Tesla auto-resume, proxy switch toggled elsewhere)
            # starts charging while we're not in TRACKING. Debounce skips
            # the BLE call once _commanded_amps is already 0.
            if plugged_in:
                await self._send_amps(0)
            await self._send_switch(on=False)
        
        return self._build_data_dict(
            production_w=production_w,
            consumption_w=consumption_w,
            excess_w=excess_w,
            excess_w_pre_battery=excess_w_pre_battery,
            battery_deduction_w=battery_deduction_w,
            plugged_in=plugged_in,
            target_amps=target_amps,
            battery_power_w=battery_power_w,
            battery_soc_pct=battery_soc_pct,
            battery_priority_active=battery_priority_active,
        )

    def _build_data_dict(
        self,
        production_w: float | None,
        consumption_w: float | None,
        excess_w: float | None,
        excess_w_pre_battery: float | None,
        battery_deduction_w: float,
        plugged_in: bool,
        target_amps: int | None,
        battery_power_w: float | None,
        battery_soc_pct: float | None,
        battery_priority_active: bool,
    ) -> dict[str, Any]:
        """Build the data dictionary returned by the coordinator."""
        return {
            "mode": self._mode.value,
            "controller_state": self._controller_state.value,
            "production_w": production_w,
            "consumption_w": consumption_w,
            "excess_w": excess_w,
            "excess_pre_battery_w": excess_w_pre_battery,
            "battery_deduction_w": battery_deduction_w,
            "target_amps": target_amps,
            "commanded_amps": self._commanded_amps,
            "is_charging": self._is_charging,
            "plugged_in": plugged_in,
            "seconds_until_next_transition": self._compute_seconds_until_transition(),
            "last_command_sent_at": self._last_command_sent_at,
            "last_command_succeeded": self._last_command_succeeded,
            "battery_power_w": battery_power_w,
            "battery_soc_pct": battery_soc_pct,
            "battery_priority_active": battery_priority_active,
        }
