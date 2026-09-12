"""
Predefined visual style templates for subtitle rendering.
Supports standard YouTube/Bilibili, TikTok/Shorts vertical viral, Cinema, and Dual-Language presets.
"""

from typing import Dict
from subtitler.plugins.base import StyleTemplate

STYLE_TEMPLATES: Dict[str, StyleTemplate] = {
    "default": StyleTemplate(
        name="default",
        description="Clean, balanced standard subtitles with crisp black outline.",
        font_name="Microsoft YaHei",
        font_size=20,
        primary_color="&H00FFFFFF",  # Pure White
        outline_color="&H00000000",  # Black outline
        bold=True,
        outline_width=2,
        shadow_depth=1,
        alignment=2,
        margin_v=28
    ),
    "bilibili_standard": StyleTemplate(
        name="bilibili_standard",
        description="High-contrast Bilibili / YouTube knowledge video style. Legible on any background.",
        font_name="Microsoft YaHei",
        font_size=22,
        primary_color="&H00FFFFFF",  # Pure White
        outline_color="&H00111111",  # Deep Charcoal Outline
        bold=True,
        outline_width=3,
        shadow_depth=1,
        alignment=2,
        margin_v=32
    ),
    "shorts_punchy": StyleTemplate(
        name="shorts_punchy",
        description="Viral TikTok / YouTube Shorts / Reels punchy style. Bold vibrant yellow accent.",
        font_name="Microsoft YaHei",
        font_size=26,
        primary_color="&H0000E6FF",  # Vibrant Punchy Yellow/Gold (BGR: &H00 + BB + GG + RR)
        outline_color="&H00000000",  # Solid Black Stroke
        bold=True,
        outline_width=4,
        shadow_depth=2,
        alignment=2,
        margin_v=60
    ),
    "cinema_minimal": StyleTemplate(
        name="cinema_minimal",
        description="Cinematic film aesthetic with elegant typography and subtle soft drop shadow.",
        font_name="SimSun",
        font_size=19,
        primary_color="&H00F5F5F5",  # Off-white / ivory
        outline_color="&H00222222",
        bold=False,
        outline_width=1,
        shadow_depth=2,
        alignment=2,
        margin_v=24
    ),
    "dual_contrast": StyleTemplate(
        name="dual_contrast",
        description="Optimized for bilingual subtitles with high readability for both upper and lower rows.",
        font_name="Microsoft YaHei",
        font_size=20,
        primary_color="&H00FFFFFF",
        outline_color="&H00000000",
        bold=True,
        outline_width=2,
        shadow_depth=1,
        alignment=2,
        margin_v=30
    )
}


def get_template(name: str) -> StyleTemplate:
    """Retrieve a style template by name, defaulting to 'default' if not found."""
    return STYLE_TEMPLATES.get(name.lower(), STYLE_TEMPLATES["default"])
