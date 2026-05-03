"""Binary sensor platform for Tesla Solar Charger."""
from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
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
    """Set up binary sensor entities."""
    coordinator = entry.runtime_data
    entities: list[_TeslaSolarChargerBaseBinarySensor] = [
        TeslaSolarChargerPluggedInBinarySensor(coordinator, entry),
        TeslaSolarChargerIsChargingBinarySensor(coordinator, entry),
        TeslaSolarChargerLastCommandBinarySensor(coordinator, entry),
    ]
    if entry.data.get("battery_power_sensor") and entry.data.get("battery_soc_sensor"):
        entities.append(
            TeslaSolarChargerBatteryPriorityBinarySensor(coordinator, entry)
        )
    async_add_entities(entities)


class _TeslaSolarChargerBaseBinarySensor(
    CoordinatorEntity[TeslaSolarChargerCoordinator], BinarySensorEntity
):
    """Base class for Tesla Solar Charger binary sensors."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: TeslaSolarChargerCoordinator,
        entry: ConfigEntry,
        key: str,
    ) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_{key}"

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self._entry.entry_id)},
            name=self._entry.title,
            manufacturer="Tesla Solar Charger",
            model="Solar Charger Controller",
        )


class TeslaSolarChargerPluggedInBinarySensor(_TeslaSolarChargerBaseBinarySensor):
    """Binary sensor: car plugged in (IEC 61851 says any plugged state)."""

    _attr_translation_key = "plugged_in"
    _attr_device_class = BinarySensorDeviceClass.PLUG

    def __init__(
        self,
        coordinator: TeslaSolarChargerCoordinator,
        entry: ConfigEntry,
    ) -> None:
        super().__init__(coordinator, entry, "plugged_in")

    @property
    def is_on(self) -> bool:
        return bool(self.coordinator.data.get("plugged_in", False))


class TeslaSolarChargerIsChargingBinarySensor(_TeslaSolarChargerBaseBinarySensor):
    """Binary sensor: charging switch is on."""

    _attr_translation_key = "is_charging"
    _attr_device_class = BinarySensorDeviceClass.BATTERY_CHARGING

    def __init__(
        self,
        coordinator: TeslaSolarChargerCoordinator,
        entry: ConfigEntry,
    ) -> None:
        super().__init__(coordinator, entry, "is_charging")

    @property
    def is_on(self) -> bool:
        return bool(self.coordinator.data.get("is_charging", False))


class TeslaSolarChargerLastCommandBinarySensor(_TeslaSolarChargerBaseBinarySensor):
    """Binary sensor: last BLE command succeeded.

    Returns None until the integration has issued at least one command.
    """

    _attr_translation_key = "last_command_succeeded"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(
        self,
        coordinator: TeslaSolarChargerCoordinator,
        entry: ConfigEntry,
    ) -> None:
        super().__init__(coordinator, entry, "last_command_succeeded")

    @property
    def is_on(self) -> bool | None:
        return self.coordinator.data.get("last_command_succeeded")


class TeslaSolarChargerBatteryPriorityBinarySensor(_TeslaSolarChargerBaseBinarySensor):
    """Binary sensor: battery priority is gating EV charging this cycle."""

    _attr_translation_key = "battery_priority_active"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(
        self,
        coordinator: TeslaSolarChargerCoordinator,
        entry: ConfigEntry,
    ) -> None:
        super().__init__(coordinator, entry, "battery_priority_active")

    @property
    def is_on(self) -> bool:
        return bool(self.coordinator.data.get("battery_priority_active", False))
