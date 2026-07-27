"""Switch platform for Tesla Solar Charger."""
from __future__ import annotations

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import TeslaSolarChargerConfigEntry
from .const import DEFAULT_TIME_WINDOW_ENABLED, DOMAIN
from .coordinator import TeslaSolarChargerCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: TeslaSolarChargerConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up switch entities."""
    coordinator = entry.runtime_data
    async_add_entities(
        [
            TeslaSolarChargerMasterSwitch(coordinator, entry),
            TeslaSolarChargerTimeWindowSwitch(coordinator, entry),
        ]
    )


class TeslaSolarChargerMasterSwitch(CoordinatorEntity[TeslaSolarChargerCoordinator], SwitchEntity):
    """Switch entity for master enable."""

    _attr_has_entity_name = True
    _attr_translation_key = "master_enable"

    def __init__(
        self,
        coordinator: TeslaSolarChargerCoordinator,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the switch entity."""
        super().__init__(coordinator)
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_master_enable"

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
    def is_on(self) -> bool:
        """Return True if master enable is on."""
        return self.coordinator.master_enabled

    async def async_turn_on(self, **kwargs) -> None:
        """Turn on master enable."""
        self.coordinator.master_enabled = True
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs) -> None:
        """Turn off master enable."""
        self.coordinator.master_enabled = False
        await self.coordinator.async_request_refresh()


class TeslaSolarChargerTimeWindowSwitch(
    CoordinatorEntity[TeslaSolarChargerCoordinator], SwitchEntity
):
    """Enable/disable cheap-rate time-window charging.

    Unlike the master enable (in-memory), this persists to entry.options so
    the schedule survives a restart.
    """

    _attr_has_entity_name = True
    _attr_translation_key = "time_window_enabled"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(
        self,
        coordinator: TeslaSolarChargerCoordinator,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the switch entity."""
        super().__init__(coordinator)
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_time_window_enabled"

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
    def is_on(self) -> bool:
        """Return True if time-window charging is enabled."""
        return bool(
            self._entry.options.get(
                "time_window_enabled", DEFAULT_TIME_WINDOW_ENABLED
            )
        )

    async def _async_set(self, enabled: bool) -> None:
        new_options = {**self._entry.options, "time_window_enabled": enabled}
        self.hass.config_entries.async_update_entry(self._entry, options=new_options)
        await self.coordinator.async_request_refresh()

    async def async_turn_on(self, **kwargs) -> None:
        """Enable time-window charging."""
        await self._async_set(True)

    async def async_turn_off(self, **kwargs) -> None:
        """Disable time-window charging."""
        await self._async_set(False)
