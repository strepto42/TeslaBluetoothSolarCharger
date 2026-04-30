"""Select platform for Tesla Solar Charger."""
from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import TeslaSolarChargerConfigEntry
from .const import DOMAIN, Mode
from .coordinator import TeslaSolarChargerCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: TeslaSolarChargerConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up select entities."""
    coordinator = entry.runtime_data
    async_add_entities([TeslaSolarChargerModeSelect(coordinator, entry)])


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
        for mode in Mode:
            if mode.value == option:
                self.coordinator.mode = mode
                break
        await self.coordinator.async_request_refresh()
