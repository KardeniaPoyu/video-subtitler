"""
Speech Recognition (ASR) module powered by faster-whisper.
Automatically detects hardware acceleration (CUDA / CPU) and optimizes compute type.
"""

import os
from typing import List, Dict, Any, Optional
from dataclasses import dataclass


@dataclass
class SubtitleSegment:
    start: float  # In seconds
    end: float    # In seconds
    text: str


class WhisperTranscriber:
    def __init__(
        self,
        model_size: str = "small",
        device: Optional[str] = None,
        compute_type: Optional[str] = None,
        download_root: Optional[str] = None
    ):
        """
        Initialize the Faster-Whisper model.
        
        :param model_size: 'tiny', 'base', 'small', 'medium', 'large-v3'
        :param device: 'cuda', 'cpu', or auto-detect if None
        :param compute_type: 'int8', 'float16', 'int8_float16', etc.
        :param download_root: Path to cache models.
        """
        from faster_whisper import WhisperModel
        import torch

        if device is None:
            device = "cuda" if torch.cuda.is_available() else "cpu"

        if compute_type is None:
            compute_type = "float16" if device == "cuda" else "int8"

        self.device = device
        self.compute_type = compute_type
        self.model_size = model_size

        print(f"[WhisperTranscriber] Loading model '{model_size}' on {device.upper()} ({compute_type})...")
        try:
            self.model = WhisperModel(
                model_size_or_path=model_size,
                device=device,
                compute_type=compute_type,
                download_root=download_root
            )
        except Exception as e:
            if device == "cuda":
                print(f"[WhisperTranscriber] CUDA initialization failed ({e}). Falling back to CPU...")
                self.device = "cpu"
                self.compute_type = "int8"
                self.model = WhisperModel(
                    model_size_or_path=model_size,
                    device="cpu",
                    compute_type="int8",
                    download_root=download_root
                )
            else:
                raise e

    def transcribe(
        self,
        audio_path: str,
        language: Optional[str] = None,
        beam_size: int = 5,
        vad_filter: bool = True,
        initial_prompt: Optional[str] = None
    ) -> List[SubtitleSegment]:
        """
        Transcribe an audio file and return a list of SubtitleSegments.
        """
        if not os.path.exists(audio_path):
            raise FileNotFoundError(f"Audio file not found: {audio_path}")

        print(f"[WhisperTranscriber] Transcribing {os.path.basename(audio_path)}...")
        segments, info = self.model.transcribe(
            audio_path,
            language=language,
            beam_size=beam_size,
            vad_filter=vad_filter,
            vad_parameters=dict(min_silence_duration_ms=500),
            initial_prompt=initial_prompt
        )

        detected_lang = info.language
        prob = info.language_probability
        print(f"[WhisperTranscriber] Detected language: {detected_lang} (probability: {prob:.2f})")

        results: List[SubtitleSegment] = []
        for s in segments:
            text = s.text.strip()
            if text:
                results.append(SubtitleSegment(start=s.start, end=s.end, text=text))

        print(f"[WhisperTranscriber] Transcribed {len(results)} segments.")
        return results
