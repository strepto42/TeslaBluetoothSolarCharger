"""Time platform for Tesla Solar Charger.

Start/end of the cheap-rate charging window. Both persist to
`entry.options` so the schedule survives restarts.
"""
from __future__ import annotations

from datetime import time as dt_time

from homeassistant.components.time import TimeEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from . import TeslaSolarChargerConfigEntry
from .const import (
    DEFAULT_TIME_WINDOW_END,
    DEFAULT_TIME_WINDOW_START,
    DOMAIN,
)
from .coordinator import TeslaSolarChargerCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: TeslaSolarChargerConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up time entities."""
    coordinator = entry.runtime_data
    async_add_entities(
        [
            TeslaSolarChargerChargeWindowStartTime(coordinator, entry),
            TeslaSolarChargerChargeWindowEndTime(coordinator, entry),
        ]
    )


class _TeslaSolarChargerBaseTime(
    CoordinatorEntity[TeslaSolarChargerCoordinator], TimeEntity
):
    """Base class for Tesla Solar Charger time entities."""

    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(
        self,
        coordinator: TeslaSolarChargerCoordinator,
        entry: ConfigEntry,
        key: str,
        default: str,
    ) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._key = key
        self._default = default
        self._attr_unique_id = f"{entry.entry_id}_{key}"

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self._entry.entry_id)},
            name=self._entry.title,
            manufacturer="Tesla Solar Charger",
            model="Solar Charger Controller",
        )

    @property
    def native_value(self) -> dt_time | None:
        """Return the configured time.

        An unset option shows the default. A corrupt one returns None
        (rendered as unknown) rather than masking it with the default —
        the coordinator disables the window in that case, so the display
        must not imply a working schedule.
        """
        if self._key not in self._entry.options:
            return dt_util.parse_time(self._default)
        raw = self._entry.options[self._key]
        if isinstance(raw, dt_time):
            return raw
        return dt_util.parse_time(raw) if isinstance(raw, str) else None

    async def async_set_value(self, value: dt_time) -> None:
        """Persist the new time to entry.options."""
        new_options = {**self._entry.options, self._key: value.isoformat()}
        self.hass.config_entries.async_update_entry(self._entry, options=new_options)
        await self.coordinator.async_request_refresh()


class TeslaSolarChargerChargeWindowStartTime(_TeslaSolarChargerBaseTime):
    """Start of the cheap-rate charging window."""

    _attr_translation_key = "time_window_start"

    def __init__(
        self,
        coordinator: TeslaSolarChargerCoordinator,
        entry: ConfigEntry,
    ) -> None:
        super().__init__(
            coordinator, entry, "time_window_start", DEFAULT_TIME_WINDOW_START
        )


class TeslaSolarChargerChargeWindowEndTime(_TeslaSolarChargerBaseTime):
    """End of the cheap-rate charging window."""

    _attr_translation_key = "time_window_end"

    def __init__(
        self,
        coordinator: TeslaSolarChargerCoordinator,
        entry: ConfigEntry,
    ) -> None:
        super().__init__(
            coordinator, entry, "time_window_end", DEFAULT_TIME_WINDOW_END
        )
