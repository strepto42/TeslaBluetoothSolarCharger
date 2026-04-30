"""Sensor platform for Tesla Solar Charger."""
from __future__ import annotations

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfElectricCurrent, UnitOfPower, UnitOfTime
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
        TeslaSolarChargerLastCommandSensor(coordinator, entry),
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


class TeslaSolarChargerLastCommandSensor(TeslaSolarChargerBaseSensor):
    """Sensor for last command status."""

    _attr_translation_key = "last_command_succeeded"

    def __init__(
        self,
        coordinator: TeslaSolarChargerCoordinator,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, entry, "last_command_succeeded")

    @property
    def native_value(self) -> str | None:
        """Return last command status as on/off string."""
        succeeded = self.coordinator.data.get("last_command_succeeded")
        if succeeded is None:
            return None
        return "on" if succeeded else "off"
