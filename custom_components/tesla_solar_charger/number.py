"""Number platform for Tesla Solar Charger."""
from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfElectricCurrent, UnitOfPower
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import TeslaSolarChargerConfigEntry
from .const import (
    AMPS_MAX_LIMIT,
    AMPS_MIN_LIMIT,
    DEFAULT_MARGIN_W,
    DEFAULT_MAX_AMPS,
    DEFAULT_MIN_AMPS,
    DOMAIN,
    MARGIN_MAX,
    MARGIN_MIN,
)
from .coordinator import TeslaSolarChargerCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: TeslaSolarChargerConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up number entities."""
    coordinator = entry.runtime_data
    async_add_entities([
        TeslaSolarChargerMinAmpsNumber(coordinator, entry),
        TeslaSolarChargerMaxAmpsNumber(coordinator, entry),
        TeslaSolarChargerMarginNumber(coordinator, entry),
    ])


class TeslaSolarChargerBaseNumber(CoordinatorEntity[TeslaSolarChargerCoordinator], NumberEntity):
    """Base class for Tesla Solar Charger number entities."""

    _attr_has_entity_name = True
    _attr_mode = NumberMode.BOX

    def __init__(
        self,
        coordinator: TeslaSolarChargerCoordinator,
        entry: ConfigEntry,
        key: str,
    ) -> None:
        """Initialize the number entity."""
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

    async def _async_update_option(self, value: float) -> None:
        """Update the config entry option."""
        new_options = {**self._entry.options, self._key: int(value)}
        self.hass.config_entries.async_update_entry(
            self._entry,
            options=new_options,
        )
        await self.coordinator.async_request_refresh()


class TeslaSolarChargerMinAmpsNumber(TeslaSolarChargerBaseNumber):
    """Number entity for minimum charging amps."""

    _attr_translation_key = "min_amps"
    _attr_native_unit_of_measurement = UnitOfElectricCurrent.AMPERE
    _attr_native_min_value = AMPS_MIN_LIMIT
    _attr_native_max_value = AMPS_MAX_LIMIT
    _attr_native_step = 1

    def __init__(
        self,
        coordinator: TeslaSolarChargerCoordinator,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the number entity."""
        super().__init__(coordinator, entry, "min_amps")

    @property
    def native_value(self) -> int:
        """Return the current value."""
        return self._entry.options.get("min_amps", DEFAULT_MIN_AMPS)

    async def async_set_native_value(self, value: float) -> None:
        """Set the value."""
        await self._async_update_option(value)


class TeslaSolarChargerMaxAmpsNumber(TeslaSolarChargerBaseNumber):
    """Number entity for maximum charging amps."""

    _attr_translation_key = "max_amps"
    _attr_native_unit_of_measurement = UnitOfElectricCurrent.AMPERE
    _attr_native_min_value = AMPS_MIN_LIMIT
    _attr_native_max_value = AMPS_MAX_LIMIT
    _attr_native_step = 1

    def __init__(
        self,
        coordinator: TeslaSolarChargerCoordinator,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the number entity."""
        super().__init__(coordinator, entry, "max_amps")

    @property
    def native_value(self) -> int:
        """Return the current value."""
        return self._entry.options.get("max_amps", DEFAULT_MAX_AMPS)

    async def async_set_native_value(self, value: float) -> None:
        """Set the value."""
        await self._async_update_option(value)


class TeslaSolarChargerMarginNumber(TeslaSolarChargerBaseNumber):
    """Number entity for solar tracking margin."""

    _attr_translation_key = "margin_w"
    _attr_native_unit_of_measurement = UnitOfPower.WATT
    _attr_native_min_value = MARGIN_MIN
    _attr_native_max_value = MARGIN_MAX
    _attr_native_step = 1

    def __init__(
        self,
        coordinator: TeslaSolarChargerCoordinator,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the number entity."""
        super().__init__(coordinator, entry, "margin_w")

    @property
    def native_value(self) -> int:
        """Return the current value."""
        return self._entry.options.get("margin_w", DEFAULT_MARGIN_W)

    async def async_set_native_value(self, value: float) -> None:
        """Set the value."""
        await self._async_update_option(value)
