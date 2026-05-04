"""Number platform for Tesla Solar Charger."""
from __future__ import annotations

from datetime import timedelta

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory, UnitOfElectricCurrent, UnitOfPower, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import TeslaSolarChargerConfigEntry
from .const import (
    AMPS_MAX_LIMIT,
    AMPS_MIN_LIMIT,
    BATTERY_PRIORITY_LIMIT_MAX,
    BATTERY_PRIORITY_LIMIT_MIN,
    DEFAULT_BATTERY_PRIORITY_CHARGE_LIMIT_PCT,
    DEFAULT_MARGIN_W,
    DEFAULT_MAX_AMPS,
    DEFAULT_MIN_AMPS,
    DEFAULT_MIN_SOLAR_GENERATION_W,
    DEFAULT_RESTART_DELAY_SECONDS,
    DEFAULT_STOP_DELAY_SECONDS,
    DEFAULT_UPDATE_INTERVAL_SECONDS,
    DOMAIN,
    MARGIN_MAX,
    MARGIN_MIN,
    MIN_SOLAR_GENERATION_MAX,
    MIN_SOLAR_GENERATION_MIN,
    UPDATE_INTERVAL_MAX,
    UPDATE_INTERVAL_MIN,
)
from .coordinator import TeslaSolarChargerCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: TeslaSolarChargerConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up number entities."""
    coordinator = entry.runtime_data
    entities: list[TeslaSolarChargerBaseNumber] = [
        TeslaSolarChargerMinAmpsNumber(coordinator, entry),
        TeslaSolarChargerMaxAmpsNumber(coordinator, entry),
        TeslaSolarChargerMarginNumber(coordinator, entry),
        TeslaSolarChargerUpdateIntervalNumber(coordinator, entry),
        TeslaSolarChargerMinSolarGenerationNumber(coordinator, entry),
        TeslaSolarChargerStopDelayNumber(coordinator, entry),
        TeslaSolarChargerRestartDelayNumber(coordinator, entry),
    ]
    if entry.data.get("battery_power_sensor") and entry.data.get("battery_soc_sensor"):
        entities.append(TeslaSolarChargerBatteryPriorityLimitNumber(coordinator, entry))
    async_add_entities(entities)


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
    _attr_entity_category = EntityCategory.CONFIG

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
    _attr_entity_category = EntityCategory.CONFIG

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
    _attr_entity_category = EntityCategory.CONFIG

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


class TeslaSolarChargerUpdateIntervalNumber(TeslaSolarChargerBaseNumber):
    """Polling interval. Setter mutates coordinator.update_interval directly."""

    _attr_translation_key = "update_interval_seconds"
    _attr_native_unit_of_measurement = UnitOfTime.SECONDS
    _attr_native_min_value = UPDATE_INTERVAL_MIN
    _attr_native_max_value = UPDATE_INTERVAL_MAX
    _attr_native_step = 1
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(
        self,
        coordinator: TeslaSolarChargerCoordinator,
        entry: ConfigEntry,
    ) -> None:
        super().__init__(coordinator, entry, "update_interval_seconds")

    @property
    def native_value(self) -> int:
        return self._entry.options.get(
            "update_interval_seconds", DEFAULT_UPDATE_INTERVAL_SECONDS
        )

    async def async_set_native_value(self, value: float) -> None:
        seconds = int(value)
        # Persist to options first…
        await self._async_update_option(seconds)
        # …and then update the live coordinator interval so the change
        # takes effect on the next scheduled cycle without a reload.
        self.coordinator.update_interval = timedelta(seconds=seconds)


class TeslaSolarChargerMinSolarGenerationNumber(TeslaSolarChargerBaseNumber):
    """Minimum solar production threshold. Solar+Grid stops below this."""

    _attr_translation_key = "min_solar_generation_w"
    _attr_native_unit_of_measurement = UnitOfPower.WATT
    _attr_native_min_value = MIN_SOLAR_GENERATION_MIN
    _attr_native_max_value = MIN_SOLAR_GENERATION_MAX
    _attr_native_step = 1
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(
        self,
        coordinator: TeslaSolarChargerCoordinator,
        entry: ConfigEntry,
    ) -> None:
        super().__init__(coordinator, entry, "min_solar_generation_w")

    @property
    def native_value(self) -> int:
        return self._entry.options.get(
            "min_solar_generation_w", DEFAULT_MIN_SOLAR_GENERATION_W
        )

    async def async_set_native_value(self, value: float) -> None:
        await self._async_update_option(value)


class TeslaSolarChargerStopDelayNumber(TeslaSolarChargerBaseNumber):
    """Seconds below threshold before STOPPING progresses to COOLDOWN."""

    _attr_translation_key = "stop_delay_seconds"
    _attr_native_unit_of_measurement = UnitOfTime.SECONDS
    _attr_native_min_value = 0
    _attr_native_max_value = 3600
    _attr_native_step = 1
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(
        self,
        coordinator: TeslaSolarChargerCoordinator,
        entry: ConfigEntry,
    ) -> None:
        super().__init__(coordinator, entry, "stop_delay_seconds")

    @property
    def native_value(self) -> int:
        return self._entry.options.get(
            "stop_delay_seconds", DEFAULT_STOP_DELAY_SECONDS
        )

    async def async_set_native_value(self, value: float) -> None:
        await self._async_update_option(value)


class TeslaSolarChargerRestartDelayNumber(TeslaSolarChargerBaseNumber):
    """COOLDOWN duration before TRACKING can restart after a stop."""

    _attr_translation_key = "restart_delay_seconds"
    _attr_native_unit_of_measurement = UnitOfTime.SECONDS
    _attr_native_min_value = 0
    _attr_native_max_value = 7200
    _attr_native_step = 1
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(
        self,
        coordinator: TeslaSolarChargerCoordinator,
        entry: ConfigEntry,
    ) -> None:
        super().__init__(coordinator, entry, "restart_delay_seconds")

    @property
    def native_value(self) -> int:
        return self._entry.options.get(
            "restart_delay_seconds", DEFAULT_RESTART_DELAY_SECONDS
        )

    async def async_set_native_value(self, value: float) -> None:
        await self._async_update_option(value)


class TeslaSolarChargerBatteryPriorityLimitNumber(TeslaSolarChargerBaseNumber):
    """Home-battery SoC at/above which excess goes to EV (battery aware)."""

    _attr_translation_key = "battery_priority_charge_limit_pct"
    _attr_native_unit_of_measurement = "%"
    _attr_native_min_value = BATTERY_PRIORITY_LIMIT_MIN
    _attr_native_max_value = BATTERY_PRIORITY_LIMIT_MAX
    _attr_native_step = 1
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(
        self,
        coordinator: TeslaSolarChargerCoordinator,
        entry: ConfigEntry,
    ) -> None:
        super().__init__(coordinator, entry, "battery_priority_charge_limit_pct")

    @property
    def native_value(self) -> int:
        return self._entry.options.get(
            "battery_priority_charge_limit_pct",
            DEFAULT_BATTERY_PRIORITY_CHARGE_LIMIT_PCT,
        )

    async def async_set_native_value(self, value: float) -> None:
        await self._async_update_option(value)
