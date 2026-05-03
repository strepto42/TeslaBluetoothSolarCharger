"""Sensor platform for Tesla Solar Charger."""
from __future__ import annotations

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory, UnitOfElectricCurrent, UnitOfPower, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import TeslaSolarChargerConfigEntry
from .const import DOMAIN
from .coordinator import TeslaSolarChargerCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: TeslaSolarChargerConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up sensor entities."""
    coordinator = entry.runtime_data
    async_add_entities([
        TeslaSolarChargerTargetAmpsSensor(coordinator, entry),
        TeslaSolarChargerCommandedAmpsSensor(coordinator, entry),
        TeslaSolarChargerExcessSolarSensor(coordinator, entry),
        TeslaSolarChargerStateSensor(coordinator, entry),
        TeslaSolarChargerTransitionSensor(coordinator, entry),
        TeslaSolarChargerProductionSensor(coordinator, entry),
        TeslaSolarChargerConsumptionSensor(coordinator, entry),
        TeslaSolarChargerDiagnosticsSensor(coordinator, entry),
    ])


class TeslaSolarChargerBaseSensor(CoordinatorEntity[TeslaSolarChargerCoordinator], SensorEntity):
    """Base class for Tesla Solar Charger sensors."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: TeslaSolarChargerCoordinator,
        entry: ConfigEntry,
        key: str,
    ) -> None:
        """Initialize the sensor entity."""
        super().__init__(coordinator)
        self._entry = entry
        self._key = key
        self._attr_unique_id = f"{entry.entry_id}_{key}"

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info."""
        return DeviceInfo(
            identifiers={(DOMAIN, self._entry.entry_id)},
            name=self._entry.title,
            manufacturer="Tesla Solar Charger",
            model="Solar Charger Controller",
        )


class TeslaSolarChargerTargetAmpsSensor(TeslaSolarChargerBaseSensor):
    """Sensor for target charging amps."""

    _attr_translation_key = "target_amps"
    _attr_native_unit_of_measurement = UnitOfElectricCurrent.AMPERE
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(
        self,
        coordinator: TeslaSolarChargerCoordinator,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, entry, "target_amps")

    @property
    def native_value(self) -> int | None:
        """Return the target amps."""
        return self.coordinator.data.get("target_amps")


class TeslaSolarChargerCommandedAmpsSensor(TeslaSolarChargerBaseSensor):
    """Sensor for commanded charging amps."""

    _attr_translation_key = "commanded_amps"
    _attr_native_unit_of_measurement = UnitOfElectricCurrent.AMPERE

    def __init__(
        self,
        coordinator: TeslaSolarChargerCoordinator,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, entry, "commanded_amps")

    @property
    def native_value(self) -> int | None:
        """Return the commanded amps."""
        return self.coordinator.data.get("commanded_amps")


class TeslaSolarChargerExcessSolarSensor(TeslaSolarChargerBaseSensor):
    """Sensor for excess solar power."""

    _attr_translation_key = "excess_solar"
    _attr_native_unit_of_measurement = UnitOfPower.WATT
    _attr_device_class = SensorDeviceClass.POWER
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(
        self,
        coordinator: TeslaSolarChargerCoordinator,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, entry, "excess_solar")

    @property
    def native_value(self) -> float | None:
        """Return the excess solar power."""
        return self.coordinator.data.get("excess_w")


class TeslaSolarChargerStateSensor(TeslaSolarChargerBaseSensor):
    """Sensor for controller state."""

    _attr_translation_key = "controller_state"

    def __init__(
        self,
        coordinator: TeslaSolarChargerCoordinator,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, entry, "controller_state")

    @property
    def native_value(self) -> str | None:
        """Return the controller state."""
        return self.coordinator.data.get("controller_state")


class TeslaSolarChargerTransitionSensor(TeslaSolarChargerBaseSensor):
    """Sensor for seconds until next transition."""

    _attr_translation_key = "seconds_until_next_transition"
    _attr_native_unit_of_measurement = UnitOfTime.SECONDS

    def __init__(
        self,
        coordinator: TeslaSolarChargerCoordinator,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, entry, "seconds_until_next_transition")

    @property
    def native_value(self) -> int | None:
        """Return seconds until next transition."""
        return self.coordinator.data.get("seconds_until_next_transition")


class TeslaSolarChargerProductionSensor(TeslaSolarChargerBaseSensor):
    """Sensor for solar production reading."""

    _attr_translation_key = "production"
    _attr_native_unit_of_measurement = UnitOfPower.WATT
    _attr_device_class = SensorDeviceClass.POWER
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(
        self,
        coordinator: TeslaSolarChargerCoordinator,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, entry, "production")

    @property
    def native_value(self) -> float | None:
        """Return solar production."""
        return self.coordinator.data.get("production_w")


class TeslaSolarChargerConsumptionSensor(TeslaSolarChargerBaseSensor):
    """Sensor for home consumption reading."""

    _attr_translation_key = "consumption"
    _attr_native_unit_of_measurement = UnitOfPower.WATT
    _attr_device_class = SensorDeviceClass.POWER
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(
        self,
        coordinator: TeslaSolarChargerCoordinator,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, entry, "consumption")

    @property
    def native_value(self) -> float | None:
        """Return home consumption."""
        return self.coordinator.data.get("consumption_w")


class TeslaSolarChargerDiagnosticsSensor(TeslaSolarChargerBaseSensor):
    """Sensor with full diagnostics as attributes."""

    _attr_translation_key = "diagnostics"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(
        self,
        coordinator: TeslaSolarChargerCoordinator,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, entry, "diagnostics")

    @property
    def native_value(self) -> str:
        """Return a summary status."""
        data = self.coordinator.data or {}
        mode = data.get("mode", "unknown")
        state = data.get("controller_state", "unknown")
        return f"{mode} / {state}"

    @property
    def extra_state_attributes(self) -> dict:
        """Return all diagnostic data as attributes."""
        data = self.coordinator.data or {}
        entry_data = self._entry.data or {}
        entry_options = self._entry.options or {}

        return {
            # Current state
            "mode": data.get("mode"),
            "controller_state": data.get("controller_state"),
            "master_enabled": self.coordinator.master_enabled,

            # Sensor readings
            "production_w": data.get("production_w"),
            "consumption_w": data.get("consumption_w"),
            "excess_w": data.get("excess_w"),

            # Charging state
            "plugged_in": data.get("plugged_in"),
            "is_charging": data.get("is_charging"),
            "target_amps": data.get("target_amps"),
            "commanded_amps": data.get("commanded_amps"),

            # Timers
            "seconds_until_next_transition": data.get("seconds_until_next_transition"),

            # Last command
            "last_command_succeeded": data.get("last_command_succeeded"),
            "last_command_sent_at": data.get("last_command_sent_at"),

            # Configuration
            "config_production_sensor": entry_data.get("production_sensor"),
            "config_consumption_sensors": entry_data.get("consumption_sensors"),
            "config_amps_number": entry_data.get("amps_number"),
            "config_charging_switch": entry_data.get("charging_switch"),
            "config_charging_state_sensor": entry_data.get("charging_state_sensor"),
            "config_voltage": entry_data.get("voltage"),
            "config_min_amps": entry_options.get("min_amps"),
            "config_max_amps": entry_options.get("max_amps"),
            "config_margin_w": entry_options.get("margin_w"),
        }


