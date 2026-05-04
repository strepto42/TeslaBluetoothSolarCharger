"""Select platform for Tesla Solar Charger."""
from __future__ import annotations

import logging

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import TeslaSolarChargerConfigEntry
from .const import (
    BATTERY_PRIORITY_STYLES,
    DEFAULT_BATTERY_PRIORITY_STYLE,
    DOMAIN,
    Mode,
)
from .coordinator import TeslaSolarChargerCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: TeslaSolarChargerConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up select entities."""
    coordinator = entry.runtime_data
    entities: list[SelectEntity] = [TeslaSolarChargerModeSelect(coordinator, entry)]
    if entry.data.get("battery_power_sensor") and entry.data.get("battery_soc_sensor"):
        entities.append(
            TeslaSolarChargerBatteryPriorityStyleSelect(coordinator, entry)
        )
    async_add_entities(entities)


class TeslaSolarChargerModeSelect(CoordinatorEntity[TeslaSolarChargerCoordinator], SelectEntity):
    """Select entity for charging mode."""

    _attr_has_entity_name = True
    _attr_translation_key = "mode"

    def __init__(
        self,
        coordinator: TeslaSolarChargerCoordinator,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the select entity."""
        super().__init__(coordinator)
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_mode"
        self._attr_options = [mode.value for mode in Mode]

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info."""
        return DeviceInfo(
            identifiers={(DOMAIN, self._entry.entry_id)},
            name=self._entry.title,
            manufacturer="Tesla Solar Charger",
            model="Solar Charger Controller",
        )

    @property
    def current_option(self) -> str | None:
        """Return current selected option."""
        return self.coordinator.mode.value

    async def async_select_option(self, option: str) -> None:
        """Handle option selection."""
        _LOGGER.info("Mode selection requested: %s", option)
        for mode in Mode:
            if mode.value == option:
                self.coordinator.mode = mode
                _LOGGER.info("Mode set to: %s, triggering refresh", mode.value)
                break
        await self.coordinator.async_request_refresh()


class TeslaSolarChargerBatteryPriorityStyleSelect(
    CoordinatorEntity[TeslaSolarChargerCoordinator], SelectEntity
):
    """Select between hard_cutoff and graduated battery priority styles."""

    _attr_has_entity_name = True
    _attr_translation_key = "battery_priority_style"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(
        self,
        coordinator: TeslaSolarChargerCoordinator,
        entry: ConfigEntry,
    ) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_battery_priority_style"
        self._attr_options = list(BATTERY_PRIORITY_STYLES)

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self._entry.entry_id)},
            name=self._entry.title,
            manufacturer="Tesla Solar Charger",
            model="Solar Charger Controller",
        )

    @property
    def current_option(self) -> str:
        return self._entry.options.get(
            "battery_priority_style", DEFAULT_BATTERY_PRIORITY_STYLE
        )

    async def async_select_option(self, option: str) -> None:
        if option not in BATTERY_PRIORITY_STYLES:
            return
        new_options = {**self._entry.options, "battery_priority_style": option}
        self.hass.config_entries.async_update_entry(
            self._entry, options=new_options
        )
        await self.coordinator.async_request_refresh()
