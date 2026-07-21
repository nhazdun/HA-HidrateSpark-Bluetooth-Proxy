"""Base entity for HidrateSpark sensors and binary sensors."""

from __future__ import annotations

from homeassistant.core import callback
from homeassistant.helpers.device_registry import CONNECTION_BLUETOOTH, DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import Entity

from .const import DOMAIN
from .coordinator import HidrateSparkCoordinator


class HidrateSparkEntity(Entity):
    """Common bits for every entity belonging to a bottle."""

    _attr_should_poll = False
    _attr_has_entity_name = True

    def __init__(self, coordinator: HidrateSparkCoordinator, key: str) -> None:
        self._coordinator = coordinator
        # Key entity + device identity on the stable device_id (survives MAC
        # rotation) and fall back to the address only if no stable id exists.
        stable = getattr(coordinator, "device_id", "") or coordinator.address
        self._attr_unique_id = f"{stable}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, stable)},
            connections={(CONNECTION_BLUETOOTH, coordinator.address)},
            name=coordinator.name or "HidrateSpark",
            manufacturer="HidrateSpark",
            model="Smart Water Bottle",
        )

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass, self._coordinator.signal, self._handle_update
            )
        )

    @callback
    def _handle_update(self) -> None:
        self.async_write_ha_state()

    @property
    def available(self) -> bool:
        return self._coordinator.connected
