"""Pillow renderer. Run only in HA's executor, never on the event loop."""

from io import BytesIO
from pathlib import Path
import unicodedata

from PIL import Image, ImageDraw, ImageFont

FONT_PATH = Path(__file__).parent / "fonts" / "NotoSansTC.ttf"


def validate_message(value: object) -> str:
    """Accept one literal, well-formed Unicode line; never a path or command."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError("message must be a nonempty string")
    if len(value) > 200 or any(
        unicodedata.category(char) in {"Cc", "Cs"} for char in value
    ):
        raise ValueError("message must be a single Unicode line of at most 200 characters")
    return unicodedata.normalize("NFC", value.strip())


def _font(size: int) -> ImageFont.FreeTypeFont:
    font = ImageFont.truetype(str(FONT_PATH), size)
    # This pinned Noto Sans TC file is variable, with one weight axis.
    font.set_variation_by_axes([400])
    return font


def render_png(message: str) -> bytes:
    """Render the approved source geometry with a redistributable TC font."""
    message = validate_message(message)
    image = Image.new("RGBA", (1100, 190), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle(
        (0, 0, 1099, 189), radius=30,
        fill=(17, 27, 43, 245), outline=(66, 200, 180, 255), width=3,
    )
    title_font = None
    for size in range(64, 39, -1):
        candidate = _font(size)
        if max(
            draw.textlength(message, font=candidate),
            draw.textbbox((0, 0), message, font=candidate)[2],
        ) <= 1024:
            title_font = candidate
            break
    if title_font is None:
        raise ValueError("message is too wide; shorten it (minimum source font size is 40)")
    draw.text((38, 20), message, font=title_font, fill=(255, 255, 255, 255))
    draw.text(
        (40, 110), "Claire 傳來的訊息", font=_font(31),
        fill=(220, 236, 245, 255),
    )
    output = BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()
