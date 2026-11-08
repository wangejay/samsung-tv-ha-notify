"""Single-TV config flow; configuration does not wake or contact the TV."""

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult

from .const import CONF_ENSURE_RECEIVER, CONF_HTTP_PORT, CONF_LOCAL_IP, CONF_TV_IP, CONF_UDP_PORT, DEFAULT_HTTP_PORT, DEFAULT_LOCAL_IP, DEFAULT_TV_IP, DEFAULT_UDP_PORT, DOMAIN
from .transport import private_ipv4


def _ip(value: object) -> str:
    try:
        return private_ipv4(value)
    except (ValueError, TypeError) as error:
        raise vol.Invalid("Use a literal private IPv4 address") from error


SCHEMA = vol.Schema({
    vol.Required(CONF_TV_IP, default=DEFAULT_TV_IP): str,
    vol.Required(CONF_LOCAL_IP, default=DEFAULT_LOCAL_IP): str,
    vol.Required(CONF_HTTP_PORT, default=DEFAULT_HTTP_PORT): vol.All(vol.Coerce(int), vol.Range(min=1, max=65535)),
    vol.Required(CONF_UDP_PORT, default=DEFAULT_UDP_PORT): vol.All(vol.Coerce(int), vol.Range(min=1, max=65535)),
    vol.Required(CONF_ENSURE_RECEIVER, default=False): bool,
})


class SamsungNuiNotifyConfigFlow(ConfigFlow, domain=DOMAIN):
    """Store explicit local HA HTTP address and TV UDP destination."""

    VERSION = 1

    async def async_step_user(self, user_input: dict | None = None) -> ConfigFlowResult:
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()
        errors = {}
        if user_input is not None:
            try:
                data = SCHEMA(user_input)
                data[CONF_TV_IP] = _ip(data[CONF_TV_IP])
                data[CONF_LOCAL_IP] = _ip(data[CONF_LOCAL_IP])
            except vol.Invalid:
                errors["base"] = "invalid_address"
            else:
                return self.async_create_entry(title="Samsung native TV overlay", data=data)
        return self.async_show_form(step_id="user", data_schema=SCHEMA, errors=errors)
