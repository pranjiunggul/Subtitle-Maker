"""
Subtitle Maker — Lightweight Transcription Engine
Runs faster-whisper with Silero VAD, word-level timestamps, prompt biasing,
and forced alignment.
Optimized specifically for smooth execution on laptops with 4GB RAM and standard CPUs.
"""

import os
import re
import math
import time
from typing import Dict, Any, List, Optional, Callable

from .audio import extract_audio, run_audio_diagnostics, get_media_duration
from .vocabulary import VocabularyManager
from .aligner import NarrationAligner
from .rules import AlignmentEngine, SubtitleCue

# Independent model directory inside C:\Subtitle Maker\models\faster-whisper
LOCAL_MODEL_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "models", "faster-whisper")


def get_model_cache_dir() -> str:
    os.makedirs(LOCAL_MODEL_DIR, exist_ok=True)
    return LOCAL_MODEL_DIR


def build_initial_prompt(language: str, vocabulary_terms: List[str] = None) -> str:
    """Build domain prompt to bias Whisper toward correct spelling."""
    if language == "id":
        base = "Transkripsi percakapan Bahasa Indonesia yang jelas, akurat, dan rapi."
    else:
        base = f"Transcribe conversation clearly in {language}."

    parts = [base]
    parts.append("Istilah: AI, YouTube, Instagram, TikTok, Reels, Shorts, Subtitle, Video, Audio, Script.")

    if vocabulary_terms:
        extra = ", ".join(vocabulary_terms[:20])
        parts.append(f"Kamus: {extra}.")

    return " ".join(parts)


def regroup_incomplete_segments(segments: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Regroups fragmented words separated by background pauses into natural sentences.
    """
    if not segments:
        return []

    regrouped = []
    current = None

    for seg in segments:
        if current is None:
            current = dict(seg)
            current["words"] = list(seg.get("words", []))
            continue

        text_clean = current["text"].strip()
        # If current segment ends with terminal punctuation, it is a COMPLETE sentence.
        # NEVER merge across sentence boundaries (. ! ?)!
        ends_sentence = bool(re.search(r"[.!?\u3002\uff1f\uff01][\"'\u201d\u2019)]*$", text_clean))

        time_gap = seg["start"] - current["end"]
        merged_text = current["text"] + " " + seg["text"]

        if not ends_sentence and time_gap < 1.2 and len(merged_text) < 100:
            current["text"] = merged_text.strip()
            current["end"] = seg["end"]
            current["words"].extend(seg.get("words", []))
            current["confidence"] = int((current["confidence"] + seg["confidence"]) / 2)
        else:
            regrouped.append(current)
            current = dict(seg)
            current["words"] = list(seg.get("words", []))

    if current:
        regrouped.append(current)

    for idx, seg in enumerate(regrouped):
        seg["index"] = idx

    return regrouped


class SubtitlePipeline:
    def __init__(self, model_cache_dir: Optional[str] = None):
        self.model_cache_dir = model_cache_dir or get_model_cache_dir()
        self.vocab_mgr = VocabularyManager()
        self.aligner = NarrationAligner()
        self.rule_engine = AlignmentEngine()
        self.loaded_model = None
        self.current_model_size = None

    def get_whisper_model(self, model_size: str, on_progress: Optional[Callable[[int, str], None]] = None):
        """Lazy load or reuse WhisperModel instance with 4GB RAM tuning."""
        if self.loaded_model is not None and self.current_model_size == model_size:
            return self.loaded_model

        if on_progress:
            on_progress(15, f"Memuat model Whisper '{model_size}' ke RAM...")

        from faster_whisper import WhisperModel

        # For 4GB RAM laptop: use 2 threads to keep system responsive and prevent thermal throttling
        cpu_threads = 2

        self.loaded_model = WhisperModel(
            model_size,
            device="cpu",
            compute_type="int8",     # 8-bit quantized: ~4x less RAM than float32
            cpu_threads=cpu_threads,
            download_root=self.model_cache_dir,
        )
        self.current_model_size = model_size
        return self.loaded_model

    def process(
        self,
        input_path: str,
        language: str = "auto",
        model_size: str = "auto",
        narration_text: Optional[str] = None,
        char_limit: Optional[int] = None,
        on_progress: Optional[Callable[[int, str], None]] = None
    ) -> Dict[str, Any]:
        """
        Lightweight full end-to-end subtitle generation.
        """
        def progress(pct: int, msg: str):
            if on_progress:
                on_progress(pct, msg)

        # 1. Verification
        if not os.path.isfile(input_path):
            raise FileNotFoundError(f"File tidak ditemukan: {input_path}")

        duration = get_media_duration(input_path)
        progress(5, "Mengekstrak audio via FFmpeg (16kHz PCM)...")

        # 2. Audio Extraction
        temp_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "temp")
        os.makedirs(temp_dir, exist_ok=True)
        base_name = os.path.splitext(os.path.basename(input_path))[0]
        wav_path = os.path.join(temp_dir, f"{base_name}_16k.wav")

        success = extract_audio(input_path, wav_path)
        if not success or not os.path.isfile(wav_path):
            raise RuntimeError("Ekstraksi audio FFmpeg gagal. Pastikan file media tidak rusak.")

        # 3. Audio Diagnostics
        progress(10, "Menganalisis audio...")
        diag_report = run_audio_diagnostics(wav_path)

        # 4. Model Selection (Optimized for 4GB RAM)
        # Default is 'base' which is fast, lightweight (~140MB), and has great Indonesian support
        if model_size == "auto" or not model_size:
            selected_model = "base"
        else:
            selected_model = model_size.lower()

        progress(12, f"Menggunakan model Whisper: '{selected_model}' (Hemat Memori 4GB)")

        # 5. Load Model
        model = self.get_whisper_model(selected_model, on_progress)

        # 6. Transcription with Silero VAD (Fast 4GB Configuration)
        progress(20, "Memulai transkripsi suara kata demi kata...")
        lang_param = None if language == "auto" else language
        vocab_terms = self.vocab_mgr.get_terms_for_prompt()
        initial_prompt = build_initial_prompt(lang_param or "id", vocab_terms)

        raw_segments = []
        detected_language = language

        try:
            # 4GB RAM Optimization:
            # - beam_size=1 (greedy decoding): 4x faster, 70% less RAM usage, highly accurate
            # - best_of=1: single pass, no repeated loops
            # - temperature=0.0: deterministic, zero retries
            segments_iter, info = model.transcribe(
                wav_path,
                language=lang_param,
                beam_size=1,
                best_of=1,
                temperature=0.0,
                condition_on_previous_text=False,
                vad_filter=True,
                vad_parameters=dict(
                    onset=0.25,
                    offset=0.2,
                    min_silence_duration_ms=250,
                    speech_pad_ms=200,
                    max_speech_duration_s=15.0,
                ),
                word_timestamps=True,
                initial_prompt=initial_prompt,
                hallucination_silence_threshold=2.5,
                no_speech_threshold=0.8,
            )
            detected_language = info.language or language

            for i, seg in enumerate(segments_iter):
                if duration > 0:
                    prog_pct = min(85, 20 + int((seg.end / duration) * 65))
                else:
                    prog_pct = min(85, 20 + i * 2)
                progress(prog_pct, f"Mentranskrip ({round(seg.end, 1)}s / {round(duration, 1)}s)...")

                avg_logprob = getattr(seg, "avg_logprob", 0.0)
                conf = int(math.exp(max(-3.0, min(0.0, avg_logprob))) * 100)

                words_data = []
                if hasattr(seg, "words") and seg.words:
                    for w in seg.words:
                        w_start = round(w.start, 3)
                        w_end = round(w.end, 3)
                        max_w_dur = max(0.3, min(1.4, len(w.word.strip()) * 0.08 + 0.3))
                        if w_end - w_start > max_w_dur:
                            w_end = round(w_start + max_w_dur, 3)

                        words_data.append({
                            "word": w.word.strip(),
                            "start": w_start,
                            "end": w_end,
                            "probability": round(getattr(w, "probability", 1.0), 3)
                        })

                # Apply vocabulary rules
                cleaned_text = self.vocab_mgr.apply_corrections(seg.text.strip())

                raw_segments.append({
                    "index": i,
                    "start": round(seg.start, 3),
                    "end": round(seg.end, 3),
                    "text": cleaned_text,
                    "language": detected_language,
                    "confidence": conf,
                    "words": words_data
                })

        except Exception as vad_err:
            # Fallback path if VAD filter encountered issue
            progress(25, "Melanjutkan dengan transkripsi langsung...")
            segments_iter, info = model.transcribe(
                wav_path,
                language=lang_param,
                beam_size=1,
                word_timestamps=True,
                vad_filter=False,
                initial_prompt=initial_prompt
            )
            detected_language = info.language or language
            raw_segments = []
            for i, seg in enumerate(segments_iter):
                words_data = []
                if hasattr(seg, "words") and seg.words:
                    for w in seg.words:
                        words_data.append({
                            "word": w.word.strip(),
                            "start": round(w.start, 3),
                            "end": round(w.end, 3),
                            "probability": round(getattr(w, "probability", 1.0), 3)
                        })
                cleaned_text = self.vocab_mgr.apply_corrections(seg.text.strip())
                raw_segments.append({
                    "index": i,
                    "start": round(seg.start, 3),
                    "end": round(seg.end, 3),
                    "text": cleaned_text,
                    "language": detected_language,
                    "confidence": 85,
                    "words": words_data
                })

        # 7. Regrouping incomplete words
        progress(88, "Merapikan kalimat dan pemenggalan kata...")
        regrouped = regroup_incomplete_segments(raw_segments)

        # 8. Forced Alignment (if Narration Script is provided)
        if narration_text and narration_text.strip():
            progress(92, "Menyelaraskan teks naskah narasi (Forced Alignment 100%)...")
            processed_segments = self.aligner.align(narration_text.strip(), regrouped)
        else:
            processed_segments = regrouped

        # 9. Segmentation (Rules + charLimit for Shorts/Reels or Netflix 2-lines)
        progress(95, "Menerapkan format baris & batasan karakter...")
        cues = self.rule_engine.align(processed_segments, char_limit=char_limit)

        progress(98, "Menyusun format SRT, VTT, ASS, TXT...")

        # Cleanup temp WAV
        try:
            if os.path.isfile(wav_path):
                os.remove(wav_path)
        except Exception:
            pass

        progress(100, "Selesai!")

        return {
            "success": True,
            "language": detected_language,
            "model": selected_model,
            "duration": round(duration, 1),
            "diagnostics": diag_report,
            "cues": [c.to_dict() for c in cues],
            "cues_count": len(cues),
            "has_narration": bool(narration_text and narration_text.strip()),
            "char_limit": char_limit
        }
