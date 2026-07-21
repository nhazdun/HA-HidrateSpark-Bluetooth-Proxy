"""HidrateSpark integration for Home Assistant."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .const import (
    CONF_ADDRESS,
    CONF_DEVICE_ID,
    CONF_NAME_PREFIX,
    CONF_SIZE_ML,
    DEFAULT_NAME_PREFIX,
    DEFAULT_SIZE_ML,
    DOMAIN,
)
from .coordinator import HidrateSparkCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.BINARY_SENSOR, Platform.SENSOR]


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Migrate old MAC-keyed entries to the stable device_id scheme.

    Version 1 entries were keyed on the (rotating) Bluetooth MAC address. From
    version 2 we key on a stable device_id derived from the bottle's local name
    so the binding survives MAC rotations. We derive that id from the existing
    entry title/name and adopt it as the new unique_id, falling back to the MAC
    if no usable name is available.
    """
    if entry.version >= 2:
        return True

    data = {**entry.data}
    name = (entry.title or data.get(CONF_NAME_PREFIX) or "").strip().lower()
    address = str(data.get(CONF_ADDRESS, "")).upper()
    # Prefer the bottle name (e.g. "h2o00008374"); fall back to the MAC.
    device_id = name if name.startswith(DEFAULT_NAME_PREFIX) else address.lower()
    data[CONF_DEVICE_ID] = device_id

    hass.config_entries.async_update_entry(
        entry,
        data=data,
        unique_id=device_id,
        version=2,
    )
    _LOGGER.info(
        "Migrated HidrateSpark entry to stable device_id %s (was MAC %s)",
        device_id,
        address,
    )
    return True



async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up HidrateSpark from a config entry."""
    address: str = entry.data[CONF_ADDRESS]
    device_id: str = entry.data.get(CONF_DEVICE_ID, "")
    name: str = entry.title or entry.data.get(CONF_NAME_PREFIX, DEFAULT_NAME_PREFIX)
    size_ml: int = entry.options.get(
        CONF_SIZE_ML, entry.data.get(CONF_SIZE_ML, DEFAULT_SIZE_ML)
    )

    coordinator = HidrateSparkCoordinator(
        hass=hass,
        entry=entry,
        address=address,
        name=name,
        size_ml=size_ml,
        device_id=device_id,
    )
    await coordinator.async_start()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    entry.async_on_unload(entry.add_update_listener(_async_options_updated))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        coordinator: HidrateSparkCoordinator = hass.data[DOMAIN].pop(entry.entry_id)
        await coordinator.async_stop()
    return unload_ok


async def _async_options_updated(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload the entry when options change (e.g. bottle size)."""
    await hass.config_entries.async_reload(entry.entry_id)
