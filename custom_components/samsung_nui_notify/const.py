"""Constants for the Samsung native overlay integration."""

DOMAIN = "samsung_nui_notify"
SERVICE_SEND = "send"
CONF_TV_IP = "tv_ip"
CONF_LOCAL_IP = "local_ip"
CONF_HTTP_PORT = "http_port"
CONF_UDP_PORT = "udp_port"
CONF_ENSURE_RECEIVER = "ensure_receiver"
DEFAULT_TV_IP = "192.168.10.20"
DEFAULT_LOCAL_IP = "192.168.10.10"
DEFAULT_HTTP_PORT = 8123
DEFAULT_UDP_PORT = 18110
APP_ID = "SmittyOv01.overlay"
IMAGE_PATH = "/api/samsung_nui_notify/image/{token}"
OVERLAY = {"x": 1400, "y": 40, "w": 480, "h": 83, "ms": 7000}
ACK_TIMEOUT = 9.0
IMAGE_TTL = 12.0
