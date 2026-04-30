"""Tesla Solar Charger integration."""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN, PLATFORMS
from .coordinator import TeslaSolarChargerCoordinator

if TYPE_CHECKING:
    from .coordinator import TeslaSolarChargerCoordinator

_LOGGER = logging.getLogger(__name__)

type TeslaSolarChargerConfigEntry = ConfigEntry[TeslaSolarChargerCoordinator]


async def async_setup_entry(
    hass: HomeAssistant, entry: TeslaSolarChargerConfigEntry
) -> bool:
    """Set up Tesla Solar Charger from a config entry."""
    _LOGGER.debug("Setting up Tesla Solar Charger: %s", entry.title)

    coordinator = TeslaSolarChargerCoordinator(hass, entry)

    # Store coordinator in runtime_data
    entry.runtime_data = coordinator

    # Perform initial refresh
    await coordinator.async_config_entry_first_refresh()

    # Set up platforms
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Register options update listener
    entry.async_on_unload(entry.add_update_listener(async_options_update_listener))

    _LOGGER.info("Tesla Solar Charger setup complete: %s", entry.title)
    return True


async def async_unload_entry(
    hass: HomeAssistant, entry: TeslaSolarChargerConfigEntry
) -> bool:
    """Unload a config entry."""
    _LOGGER.debug("Unloading Tesla Solar Charger: %s", entry.title)

    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if unload_ok:
        _LOGGER.info("Tesla Solar Charger unloaded: %s", entry.title)

    return unload_ok


async def async_options_update_listener(
    hass: HomeAssistant, entry: TeslaSolarChargerConfigEntry
) -> None:
    """Handle options update."""
    _LOGGER.debug("Options updated, reloading Tesla Solar Charger: %s", entry.title)
    await hass.config_entries.async_reload(entry.entry_id)

