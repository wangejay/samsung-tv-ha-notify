"""Enter a DeviceCode directly in HA, then select its authorized community."""

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.helpers import selector
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import SmartdailyAuthError, SmartdailyClient, SmartdailyError
from .const import (
    CONF_COMMUNITY_ID,
    CONF_COMMUNITY_NAME,
    CONF_DEVICE_CODE,
    CONF_TV_HOST,
    DEFAULT_TV_HOST,
    DOMAIN,
)
from .tv import private_tv_host


def code_schema(*, include_tv=False):
    """Do not prefill or echo a credential in any later form."""
    fields = {
        vol.Required(CONF_DEVICE_CODE): selector.TextSelector(
            selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
        )
    }
    if include_tv:
        fields[vol.Required(CONF_TV_HOST, default=DEFAULT_TV_HOST)] = selector.TextSelector()
    return vol.Schema(fields)


class SmartdailyConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Use the same documented-by-upstream token/community reads as runtime."""

    VERSION = 1

    def __init__(self) -> None:
        self._device_code = ""
        self._tv_host = DEFAULT_TV_HOST
        self._communities: dict[str, str] = {}

    async def _validate_code(self, device_code: str) -> dict[str, str]:
        client = SmartdailyClient(async_get_clientsession(self.hass), device_code)
        return await client.communities()

    async def async_step_user(self, user_input=None):
        errors = {}
        if user_input is not None:
            code = user_input[CONF_DEVICE_CODE].strip()
            try:
                self._tv_host = private_tv_host(user_input.get(CONF_TV_HOST, DEFAULT_TV_HOST))
            except ValueError:
                errors["base"] = "invalid_tv_host"
            if errors:
                pass
            elif not code:
                errors["base"] = "invalid_auth"
            else:
                try:
                    communities = await self._validate_code(code)
                except SmartdailyAuthError:
                    errors["base"] = "invalid_auth"
                except SmartdailyError:
                    errors["base"] = "cannot_connect"
                else:
                    if not communities:
                        errors["base"] = "no_communities"
                    else:
                        self._device_code = code
                        self._communities = communities
                        return await self.async_step_community()
        return self.async_show_form(
            step_id="user", data_schema=code_schema(include_tv=True), errors=errors
        )

    async def async_step_community(self, user_input=None):
        if user_input is not None:
            community_id = user_input[CONF_COMMUNITY_ID]
            if community_id not in self._communities:
                return self.async_abort(reason="invalid_community")
            for entry in self._async_current_entries():
                if (
                    entry.data.get(CONF_DEVICE_CODE) == self._device_code
                    and entry.data.get(CONF_COMMUNITY_ID) == community_id
                ):
                    return self.async_abort(reason="already_configured")
            community_name = self._communities[community_id]
            return self.async_create_entry(
                title=community_name,
                data={
                    CONF_DEVICE_CODE: self._device_code,
                    CONF_COMMUNITY_ID: community_id,
                    CONF_COMMUNITY_NAME: community_name,
                    CONF_TV_HOST: self._tv_host,
                },
            )
        return self.async_show_form(
            step_id="community",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_COMMUNITY_ID): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=[
                                {"value": identifier, "label": name}
                                for identifier, name in self._communities.items()
                            ],
                            mode=selector.SelectSelectorMode.DROPDOWN,
                        )
                    )
                }
            ),
        )

    async def async_step_reauth(self, entry_data):
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input=None):
        entry = self._get_reauth_entry()
        errors = {}
        if user_input is not None:
            code = user_input[CONF_DEVICE_CODE].strip()
            try:
                communities = await self._validate_code(code) if code else {}
            except SmartdailyAuthError:
                errors["base"] = "invalid_auth"
            except SmartdailyError:
                errors["base"] = "cannot_connect"
            else:
                if entry.data[CONF_COMMUNITY_ID] not in communities:
                    errors["base"] = "invalid_auth"
                else:
                    return self.async_update_reload_and_abort(
                        entry, data_updates={CONF_DEVICE_CODE: code}
                    )
        return self.async_show_form(
            step_id="reauth_confirm", data_schema=code_schema(), errors=errors
        )
