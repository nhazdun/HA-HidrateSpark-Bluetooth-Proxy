"""Config flow for the HidrateSpark integration.

Binding is keyed on a *stable* identifier (the bottle's advertised local name,
e.g. "h2o1a2b3c") instead of the Bluetooth MAC address. HidrateSpark bottles
rotate their BLE MAC for privacy, which previously caused Home Assistant to
lose the binding and require re-pairing. By using the stable name as the config
entry unique_id we keep a single device across MAC rotations, and we transparently
refresh the stored MAC whenever the same bottle is re-discovered at a new address.

Discovery sources:
  * Bluetooth - when HA's bluetooth stack (or an ESPHome proxy) sees a bottle
    advertising the HydroSync reference service or a "h2o*" local name, the
    user is offered a one-click "Configure" action.
  * Manual - the user picks from any HidrateSpark candidate currently
    advertising in range.
"""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant.components.bluetooth import (
    BluetoothServiceInfoBleak,
    async_discovered_service_info,
)
from homeassistant.config_entries import ConfigFlow, OptionsFlow
from homeassistant.data_entry_flow import FlowResult
from homeassistant.const import CONF_ADDRESS
from homeassistant.core import callback
from homeassistant.helpers import config_validation as cv

from .const import (
    CONF_DEVICE_ID,
    CONF_NAME_PREFIX,
    CONF_SIZE_ML,
    DEFAULT_NAME_PREFIX,
    DEFAULT_SIZE_ML,
    DOMAIN,
    SERVICE_REF,
)

_LOGGER = logging.getLogger(__name__)


def _looks_like_bottle(info: BluetoothServiceInfoBleak) -> bool:
    if SERVICE_REF.lower() in {u.lower() for u in info.service_uuids or []}:
        return True
    if info.name and info.name.lower().startswith(DEFAULT_NAME_PREFIX):
        return True
    return False


def _stable_id(info: BluetoothServiceInfoBleak) -> str:
    """Return a MAC-independent identifier for a bottle.

    HidrateSpark advertises a persistent local name (e.g. "h2o1a2b3c"). We use
    that as the durable key. If for some reason no name is advertised we fall
    back to the MAC so the flow still works, but the whole point is to prefer
    the stable name whenever it is available.
    """
    if info.name:
        return info.name.strip().lower()
    return info.address.upper()


class HidrateSparkConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for HidrateSpark."""

    VERSION = 2

    def __init__(self) -> None:
        self._discovery_info: BluetoothServiceInfoBleak | None = None
        self._discovered: dict[str, BluetoothServiceInfoBleak] = {}

    # ----------------------------------------------------------- bluetooth flow

    async def async_step_bluetooth(
        self, discovery_info: BluetoothServiceInfoBleak
    ) -> FlowResult:
        """Handle a bottle discovered via the bluetooth integration."""
        if not _looks_like_bottle(discovery_info):
            return self.async_abort(reason="not_supported")

        device_id = _stable_id(discovery_info)
        await self.async_set_unique_id(device_id)
        # If we already know this bottle, transparently refresh its (possibly
        # rotated) MAC address so the connection keeps working - no re-pairing.
        self._abort_if_unique_id_configured(
            updates={CONF_ADDRESS: discovery_info.address}
        )

        self._discovery_info = discovery_info
        self.context["title_placeholders"] = {
            "name": discovery_info.name or discovery_info.address,
        }
        return await self.async_step_bluetooth_confirm()

    async def async_step_bluetooth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        assert self._discovery_info is not None
        info = self._discovery_info
        if user_input is not None:
            return self.async_create_entry(
                title=info.name or info.address,
                data={
                    CONF_ADDRESS: info.address,
                    CONF_DEVICE_ID: _stable_id(info),
                    CONF_NAME_PREFIX: DEFAULT_NAME_PREFIX,
                },
                options={CONF_SIZE_ML: user_input.get(CONF_SIZE_ML, DEFAULT_SIZE_ML)},
            )
        return self.async_show_form(
            step_id="bluetooth_confirm",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_SIZE_ML, default=DEFAULT_SIZE_ML): vol.All(
                        cv.positive_int, vol.Range(min=100, max=2000)
                    ),
                }
            ),
            description_placeholders={
                "name": info.name or info.address,
            },
        )

    # ---------------------------------------------------------------- user flow

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manual setup: pick from bottles currently advertising in range."""
        if user_input is not None:
            address = user_input[CONF_ADDRESS]
            info = self._discovered.get(address)
            device_id = _stable_id(info) if info else address.upper()

            await self.async_set_unique_id(device_id)
            self._abort_if_unique_id_configured(
                updates={CONF_ADDRESS: address}
            )

            title = info.name if info and info.name else address
            return self.async_create_entry(
                title=title,
                data={
                    CONF_ADDRESS: address,
                    CONF_DEVICE_ID: device_id,
                    CONF_NAME_PREFIX: DEFAULT_NAME_PREFIX,
                },
                options={CONF_SIZE_ML: user_input.get(CONF_SIZE_ML, DEFAULT_SIZE_ML)},
            )

        # Build a picker from currently-advertising candidates, skipping ones we
        # already track (matched by stable id, not MAC).
        current_ids = {
            entry.unique_id for entry in self._async_current_entries()
        }
        self._discovered = {}
        for info in async_discovered_service_info(self.hass):
            if not _looks_like_bottle(info):
                continue
            if _stable_id(info) in current_ids:
                continue
            self._discovered[info.address] = info

        if not self._discovered:
            return self.async_abort(reason="no_devices_found")

        choices = {
            addr: f"{(info.name or addr)} ({addr})"
            for addr, info in self._discovered.items()
        }
        schema = vol.Schema(
            {
                vol.Required(CONF_ADDRESS): vol.In(choices),
                vol.Required(CONF_SIZE_ML, default=DEFAULT_SIZE_ML): vol.All(
                    cv.positive_int, vol.Range(min=100, max=2000)
                ),
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema)

    # ----------------------------------------------------------------- options

    @staticmethod
    @callback
    def async_get_options_flow(config_entry) -> OptionsFlow:
        return HidrateSparkOptionsFlow(config_entry)


class HidrateSparkOptionsFlow(OptionsFlow):
    """Allow the bottle size to be tuned after setup."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)
        current = self.config_entry.options.get(
            CONF_SIZE_ML, self.config_entry.data.get(CONF_SIZE_ML, DEFAULT_SIZE_ML)
        )
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_SIZE_ML, default=current): vol.All(
                        cv.positive_int, vol.Range(min=100, max=2000)
                    ),
                }
            ),
        )
