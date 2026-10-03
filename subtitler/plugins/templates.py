"""
Predefined visual style templates for subtitle rendering.
Supports standard YouTube/Bilibili, TikTok/Shorts vertical viral, Cinema, and Dual-Language presets.
Anchored to 1920x1080 canvas with safe edge margins.
"""

from typing import Dict
from subtitler.plugins.base import StyleTemplate

STYLE_TEMPLATES: Dict[str, StyleTemplate] = {
    "default": StyleTemplate(
        name="default",
        description="Clean, balanced standard subtitles with crisp black outline.",
        font_name="Microsoft YaHei",
        font_size=38,
        primary_color="&H00FFFFFF",  # Pure White
        outline_color="&H00000000",  # Black outline
        bold=True,
        outline_width=3,
        shadow_depth=1,
        alignment=2,
        margin_v=45,
        margin_l=80,
        margin_r=80,
        play_res_x=1920,
        play_res_y=1080
    ),
    "bilibili_standard": StyleTemplate(
        name="bilibili_standard",
        description="High-contrast Bilibili / YouTube knowledge video style. Legible on any background.",
        font_name="Microsoft YaHei",
        font_size=42,
        primary_color="&H00FFFFFF",  # Pure White
        outline_color="&H00111111",  # Deep Charcoal Outline
        bold=True,
        outline_width=4,
        shadow_depth=1,
        alignment=2,
        margin_v=50,
        margin_l=80,
        margin_r=80,
        play_res_x=1920,
        play_res_y=1080
    ),
    "shorts_punchy": StyleTemplate(
        name="shorts_punchy",
        description="Viral TikTok / YouTube Shorts / Reels punchy style. Bold vibrant yellow accent.",
        font_name="Microsoft YaHei",
        font_size=48,
        primary_color="&H0000E6FF",  # Vibrant Punchy Yellow/Gold
        outline_color="&H00000000",  # Solid Black Stroke
        bold=True,
        outline_width=5,
        shadow_depth=2,
        alignment=2,
        margin_v=80,
        margin_l=60,
        margin_r=60,
        play_res_x=1920,
        play_res_y=1080
    ),
    "cinema_minimal": StyleTemplate(
        name="cinema_minimal",
        description="Cinematic film aesthetic with elegant typography and subtle soft drop shadow.",
        font_name="SimSun",
        font_size=34,
        primary_color="&H00F5F5F5",  # Off-white / ivory
        outline_color="&H00222222",
        bold=False,
        outline_width=2,
        shadow_depth=2,
        alignment=2,
        margin_v=40,
        margin_l=100,
        margin_r=100,
        play_res_x=1920,
        play_res_y=1080
    ),
    "dual_contrast": StyleTemplate(
        name="dual_contrast",
        description="Optimized for bilingual subtitles with high readability for both upper and lower rows.",
        font_name="Microsoft YaHei",
        font_size=36,
        primary_color="&H00FFFFFF",
        outline_color="&H00000000",
        bold=True,
        outline_width=3,
        shadow_depth=1,
        alignment=2,
        margin_v=45,
        margin_l=80,
        margin_r=80,
        play_res_x=1920,
        play_res_y=1080
    ),
    # --- Bilingual house standard (双语字阶标准): primary fs52 bold / secondary fs34 soft gray ---
    "bilingual": StyleTemplate(
        name="bilingual",
        description="双语贴边沉浸式: primary (target language) 52 bold + 3.5px border, "
                    "secondary (source) 34 regular #EAEAEA + 2.5px border, MarginV 48.",
        font_name="Microsoft YaHei",
        font_size=52,
        primary_color="&H00FFFFFF",
        outline_color="&H00000000",
        bold=True,
        outline_width=3.5,
        shadow_depth=1,
        alignment=2,
        margin_v=48,
        margin_l=80,
        margin_r=80,
        max_chars=22,
        secondary_font_size=34,
        secondary_color="&H00EAEAEA",
        secondary_outline_width=2.5,
        secondary_bold=False,
        secondary_max_chars=32,
    ),
    "bilingual_avoid": StyleTemplate(
        name="bilingual_avoid",
        description="双语避让式: same as 'bilingual' but MarginV 190 to clear burned-in author "
                    "captions / chat boxes / telops at the bottom of the source video.",
        font_name="Microsoft YaHei",
        font_size=52,
        primary_color="&H00FFFFFF",
        outline_color="&H00000000",
        bold=True,
        outline_width=3.5,
        shadow_depth=1,
        alignment=2,
        margin_v=190,
        margin_l=80,
        margin_r=80,
        max_chars=22,
        secondary_font_size=34,
        secondary_color="&H00EAEAEA",
        secondary_outline_width=2.5,
        secondary_bold=False,
        secondary_max_chars=32,
    ),
    "single_large": StyleTemplate(
        name="single_large",
        description="Single-language large subtitles (fs54 bold, 3.5px border, MarginV 48).",
        font_name="Microsoft YaHei",
        font_size=54,
        primary_color="&H00FFFFFF",
        outline_color="&H00000000",
        bold=True,
        outline_width=3.5,
        shadow_depth=1,
        alignment=2,
        margin_v=48,
        margin_l=80,
        margin_r=80,
        max_chars=22,
    ),
}


def get_template(name: str) -> StyleTemplate:
    """Retrieve a style template by name. Raises KeyError with the valid names if unknown."""
    key = (name or "default").lower()
    if key not in STYLE_TEMPLATES:
        raise KeyError(f"Unknown style '{name}'. Available: {', '.join(STYLE_TEMPLATES)}")
    return STYLE_TEMPLATES[key]
