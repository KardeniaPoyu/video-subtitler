"""
Base interfaces and data structures for video-subtitler plugins.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List, Optional, Dict, Any
from subtitler.asr import SubtitleSegment


@dataclass
class StyleTemplate:
    """Configuration for subtitle visual rendering."""
    name: str
    description: str
    font_name: str = "Microsoft YaHei"
    font_size: int = 38
    primary_color: str = "&H00FFFFFF"    # White (&HAABBGGRR)
    secondary_color: str = "&H000000FF"
    outline_color: str = "&H00000000"    # Black
    back_color: str = "&H80000000"
    bold: bool = True
    italic: bool = False
    outline_width: int = 3
    shadow_depth: int = 1
    alignment: int = 2                  # 2 = Bottom Center
    margin_v: int = 45
    margin_l: int = 80
    margin_r: int = 80
    play_res_x: int = 1920
    play_res_y: int = 1080
    extra_ass_styles: Optional[str] = None


class BasePlugin(ABC):
    """Abstract base class for all video-subtitler plugins."""
    name: str = "base"
    version: str = "0.1.0"
    description: str = ""

    def initialize(self, config: Optional[Dict[str, Any]] = None) -> None:
        """Called when plugin is initialized."""
        pass


class PostProcessPlugin(BasePlugin):
    """Plugin that enriches, corrects, or filters subtitle segments after ASR."""

    @abstractmethod
    def process(self, segments: List[SubtitleSegment]) -> List[SubtitleSegment]:
        """Transform subtitle segments."""
        pass


class TranslationPlugin(BasePlugin):
    """Plugin that translates segments into a target language or generates bilingual pairs."""

    @abstractmethod
    def translate(
        self,
        segments: List[SubtitleSegment],
        target_lang: str,
        source_lang: Optional[str] = None,
        bilingual: bool = True
    ) -> List[SubtitleSegment]:
        """Translate segments."""
        pass
