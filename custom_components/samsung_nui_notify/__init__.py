"""HA-native on-demand Samsung NUI notifications. No Mac/service dependency."""

from dataclasses import dataclass

from aiohttp import web
import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.http import HomeAssistantView

from .const import CONF_ENSURE_RECEIVER, CONF_HTTP_PORT, CONF_LOCAL_IP, CONF_TV_IP, CONF_UDP_PORT, DOMAIN, IMAGE_PATH, SERVICE_SEND
from .render import render_png, validate_message
from .transport import DeliveryError, ImageStore, Sender, Settings, check_receiver_running


@dataclass
class DomainData:
    images: ImageStore
    sender: Sender | None = None


class ImageView(HomeAssistantView):
    """Existing HA HTTP server, direct TV peer + random single-use short TTL."""

    url = IMAGE_PATH
    name = "api:samsung_nui_notify:image"
    requires_auth = False

    def __init__(self, images: ImageStore) -> None:
        self.images = images

    async def get(self, request: web.Request, token: str) -> web.StreamResponse:
        return await self.images.get(request, token)


def _message(value: object) -> str:
    try:
        return validate_message(value)
    except ValueError as error:
        raise vol.Invalid(str(error)) from error


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry[Sender]) -> bool:
    """Register one TV, one service, and one reusable HA image view."""
    if DOMAIN not in hass.data:
        data = DomainData(ImageStore())
        hass.data[DOMAIN] = data
        hass.http.register_view(ImageView(data.images))
    else:
        data = hass.data[DOMAIN]
    if data.sender is not None:
        raise HomeAssistantError("Only one Samsung native TV sender is supported")
    settings = Settings(
        tv_ip=entry.data[CONF_TV_IP], local_ip=entry.data[CONF_LOCAL_IP],
        http_port=entry.data[CONF_HTTP_PORT], udp_port=entry.data[CONF_UDP_PORT],
    )
    sender = Sender(settings, data.images)
    data.sender = sender
    entry.runtime_data = sender

    async def handle_send(call: ServiceCall) -> dict | None:
        async def render(message: str) -> bytes:
            return await hass.async_add_executor_job(render_png, message)

        async def health() -> None:
            await check_receiver_running(
                async_get_clientsession(hass), settings.tv_ip,
                ensure_receiver=entry.data.get(CONF_ENSURE_RECEIVER, False),
            )

        try:
            response = await sender.send(call.data["message"], render, health)
        except DeliveryError as error:
            raise HomeAssistantError(str(error)) from error
        return response if call.return_response else None

    hass.services.async_register(
        DOMAIN, SERVICE_SEND, handle_send,
        schema=vol.Schema({vol.Required("message"): _message}, extra=vol.PREVENT_EXTRA),
        supports_response=SupportsResponse.OPTIONAL,
    )
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry[Sender]) -> bool:
    """Drop active assets/sockets, but never stop or launch the TV receiver."""
    data: DomainData = hass.data[DOMAIN]
    sender = entry.runtime_data
    if data.sender is sender:
        data.sender = None
        hass.services.async_remove(DOMAIN, SERVICE_SEND)
    await sender.close()
    # aiohttp cannot safely remove routes from a running router. Keep the empty
    # registered view for a later reload: with no leases every URL returns 404.
    return True
