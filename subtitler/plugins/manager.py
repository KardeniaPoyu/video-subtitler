"""
Plugin Manager orchestrating the video-subtitler plugin lifecycle.
"""

from typing import List, Dict, Type, Optional, Any
from subtitler.asr import SubtitleSegment
from subtitler.plugins.base import BasePlugin, PostProcessPlugin, TranslationPlugin, StyleTemplate
from subtitler.plugins.templates import get_template, STYLE_TEMPLATES
from subtitler.plugins.corrector import LLMProofreaderPlugin
from subtitler.plugins.translator import LLMTranslatorPlugin


class PluginManager:
    def __init__(self):
        self.post_processors: List[PostProcessPlugin] = []
        self.translators: List[TranslationPlugin] = []
        self._register_default_plugins()

    def _register_default_plugins(self):
        """Register out-of-the-box plugins."""
        self.register(LLMProofreaderPlugin())
        self.register(LLMTranslatorPlugin())

    def register(self, plugin: BasePlugin):
        """Register a plugin instance into the manager."""
        if isinstance(plugin, PostProcessPlugin):
            self.post_processors.append(plugin)
            print(f"[PluginManager] Registered PostProcess plugin: {plugin.name} v{plugin.version}")
        elif isinstance(plugin, TranslationPlugin):
            self.translators.append(plugin)
            print(f"[PluginManager] Registered Translation plugin: {plugin.name} v{plugin.version}")

    def apply_post_processing(
        self,
        segments: List[SubtitleSegment],
        enable_proofread: bool = False
    ) -> List[SubtitleSegment]:
        """Runs registered post-processing plugins."""
        current_segments = segments
        for p in self.post_processors:
            if isinstance(p, LLMProofreaderPlugin) and not enable_proofread:
                continue
            current_segments = p.process(current_segments)
        return current_segments

    def apply_translation(
        self,
        segments: List[SubtitleSegment],
        target_lang: Optional[str] = None,
        source_lang: Optional[str] = None,
        bilingual: bool = True
    ) -> List[SubtitleSegment]:
        """Runs registered translation plugins."""
        if not target_lang or not self.translators:
            return segments

        # Use primary translation plugin
        primary_translator = self.translators[0]
        return primary_translator.translate(
            segments=segments,
            target_lang=target_lang,
            source_lang=source_lang,
            bilingual=bilingual
        )

    def get_style_template(self, style_name: str) -> StyleTemplate:
        """Fetch style template by name."""
        return get_template(style_name)
