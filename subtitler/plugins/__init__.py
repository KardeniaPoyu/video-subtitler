"""
Video-Subtitler Plugin System.
"""

from subtitler.plugins.base import (
    BasePlugin,
    PostProcessPlugin,
    TranslationPlugin,
    StyleTemplate,
)
from subtitler.plugins.manager import PluginManager
from subtitler.plugins.templates import STYLE_TEMPLATES, get_template
from subtitler.plugins.corrector import LLMProofreaderPlugin
from subtitler.plugins.translator import LLMTranslatorPlugin

__all__ = [
    "BasePlugin",
    "PostProcessPlugin",
    "TranslationPlugin",
    "StyleTemplate",
    "PluginManager",
    "STYLE_TEMPLATES",
    "get_template",
    "LLMProofreaderPlugin",
    "LLMTranslatorPlugin",
]
