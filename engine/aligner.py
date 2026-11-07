"""
Subtitle Maker — Precision Narration Aligner Engine (Forced Alignment)
Aligns user-provided narration script (Ground Truth) with Whisper word-level timestamps.
Features:
- Full metadata / scene header stripping ([0:00-0:15] HOOK, markdown, stage directions).
- Strictly monotonic sequence alignment (Dynamic Programming via SequenceMatcher).
- Proportional time-warp interpolation for unmatched words.
- Zero backwards timestamps, zero overlaps, and exact audio-script synchronization.
"""

import re
from typing import List, Dict, Any, Optional
import difflib


def clean_narration_script(text: str) -> str:
    """
    Strips scene headers, timing tags, speaker markers, and markdown.
    Example: '[0:00–0:15] HOOK' -> removed
    """
    lines = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        # Strip timing blocks like [0:00–0:15], [00:15], (01:23 - 02:45) followed by uppercase titles
        line = re.sub(r"^\[\d+:\d+(?:[–\-]\d+:\d+)?\]\s*[\w\s+—–\-/]*", "", line)
        line = re.sub(r"^\(\d+:\d+(?:[–\-]\d+:\d+)?\)\s*[\w\s+—–\-/]*", "", line)

        # Strip markdown headers (## Title), list bullets (- / *)
        line = re.sub(r"^#+\s*", "", line)
        line = re.sub(r"^[\*\-•]\s+", "", line)

        # Strip speaker labels (Host:, Voiceover:, Narator:)
        line = re.sub(r"^(?:Host|Voiceover|Narator|Speaker\s*\d+|Pembicara\s*\d+)\s*:\s*", "", line, flags=re.IGNORECASE)

        # Normalize unicode dashes (em-dash, en-dash) to standard dash or spaced dash
        line = line.replace("\u2014", " - ").replace("\u2013", " - ").replace("\ufffd", " ")
        # Ensure space after sentence-terminal punctuation if followed directly by a word
        line = re.sub(r"([.!?\u3002\uff1f\uff01])([A-Za-z\u00C0-\u024F\d])", r"\1 \2", line)
        line = re.sub(r"\s+", " ", line).strip()

        if line:
            lines.append(line)

    return " ".join(lines)


def normalize_token(w: str) -> str:
    """Normalize word for robust phonetic matching."""
    return re.sub(r"[^\w]", "", w.lower())


class NarrationAligner:
    """
    Monotonic Forced Aligner for Indonesian & Multilingual Subtitle Scripts.
    Guarantees strictly ascending timestamps with zero overlap.
    """

    def __init__(self):
        pass

    def align(self, narration: str, whisper_segments: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Main forced-alignment function.
        Returns segments where text is ground truth from narration, timed to audio.
        """
        if not narration or not narration.strip():
            return whisper_segments

        # Extract all whisper words
        whisper_words: List[Dict[str, Any]] = []
        for s in whisper_segments:
            if "words" in s and s["words"]:
                for w in s["words"]:
                    w_str = w.get("word", "").strip()
                    if w_str:
                        whisper_words.append({
                            "word": w_str,
                            "start": round(float(w.get("start", 0.0)), 3),
                            "end": round(float(w.get("end", 0.0)), 3),
                            "probability": float(w.get("probability", 1.0))
                        })

        if not whisper_words:
            return whisper_segments

        cleaned_text = clean_narration_script(narration)
        raw_words = cleaned_text.split()
        if not raw_words:
            return whisper_segments

        # Align words monotonically
        aligned_words = self.monotonic_align(raw_words, whisper_words)

        # Group words into clean natural segments
        aligned_segments = self.build_segments_from_words(aligned_words)
        return aligned_segments if aligned_segments else whisper_segments

    def monotonic_align(
        self,
        narration_words: List[str],
        whisper_words: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Aligns narration words to whisper words using strict monotonic sequence matching.
        Guarantees timestamps NEVER decrease.
        """
        nar_norm = [normalize_token(w) for w in narration_words]
        wh_norm = [normalize_token(w["word"]) for w in whisper_words]

        # Monotonic Global Matcher
        matcher = difflib.SequenceMatcher(None, nar_norm, wh_norm, autojunk=False)
        blocks = matcher.get_matching_blocks()

        aligned: List[Dict[str, Any]] = []
        for i, w in enumerate(narration_words):
            aligned.append({
                "word": w,
                "norm": nar_norm[i],
                "start": -1.0,
                "end": -1.0,
                "probability": 1.0,
                "matched": False
            })

        # Step 1: Assign matched blocks
        for b in blocks:
            for k in range(b.size):
                n_idx = b.a + k
                w_idx = b.b + k
                w_obj = whisper_words[w_idx]
                aligned[n_idx]["start"] = w_obj["start"]
                aligned[n_idx]["end"] = w_obj["end"]
                aligned[n_idx]["probability"] = w_obj.get("probability", 1.0)
                aligned[n_idx]["matched"] = True

        # Step 2: Local fuzzy alignment for unmatched gaps between blocks
        for b_idx in range(len(blocks) - 1):
            cur_b = blocks[b_idx]
            nxt_b = blocks[b_idx + 1]

            n_s = cur_b.a + cur_b.size
            n_e = nxt_b.a
            w_s = cur_b.b + cur_b.size
            w_e = nxt_b.b

            if (n_e > n_s) and (w_e > w_s):
                sub_matcher = difflib.SequenceMatcher(
                    None,
                    nar_norm[n_s:n_e],
                    wh_norm[w_s:w_e],
                    autojunk=False
                )
                for lb in sub_matcher.get_matching_blocks():
                    for k in range(lb.size):
                        target_n = n_s + lb.a + k
                        target_w = w_s + lb.b + k
                        w_obj = whisper_words[target_w]
                        aligned[target_n]["start"] = w_obj["start"]
                        aligned[target_n]["end"] = w_obj["end"]
                        aligned[target_n]["probability"] = w_obj.get("probability", 1.0)
                        aligned[target_n]["matched"] = True

        # Step 3: Interpolate timestamps for unmatched words between anchors
        anchors = [i for i, w in enumerate(aligned) if w["matched"] and w["start"] >= 0]

        if not anchors:
            # Fallback uniform distribution
            cur_t = 0.0
            for w in aligned:
                w["start"] = round(cur_t, 3)
                w["end"] = round(cur_t + 0.32, 3)
                cur_t += 0.32
            return aligned

        # Prefix interpolation (before first anchor)
        first_a = anchors[0]
        if first_a > 0:
            first_start = aligned[first_a]["start"]
            span = max(0.2, first_start)
            step = span / (first_a + 1)
            for i in range(first_a):
                aligned[i]["start"] = round(i * step, 3)
                aligned[i]["end"] = round((i + 1) * step, 3)

        # In-between anchors interpolation (weighted by character length)
        for a_idx in range(len(anchors) - 1):
            idx1 = anchors[a_idx]
            idx2 = anchors[a_idx + 1]
            gap_len = idx2 - idx1 - 1
            if gap_len <= 0:
                continue

            t1 = aligned[idx1]["end"]
            t2 = aligned[idx2]["start"]

            # Prevent overlap between anchors
            if t2 <= t1:
                t1 = max(0.0, aligned[idx1]["start"] + 0.08)
                aligned[idx1]["end"] = t1
                t2 = max(t1 + 0.08, t2)
                aligned[idx2]["start"] = t2

            span = t2 - t1
            # Weight slot by length of word for natural pacing
            gap_words = aligned[idx1 + 1 : idx2]
            total_chars = sum(max(1, len(w["word"])) for w in gap_words)
            cur_t = t1

            for w in gap_words:
                w_share = (max(1, len(w["word"])) / total_chars) * span
                w["start"] = round(cur_t, 3)
                w["end"] = round(cur_t + w_share, 3)
                cur_t += w_share

        # Suffix interpolation (after last anchor)
        last_a = anchors[-1]
        cur_t = aligned[last_a]["end"]
        for i in range(last_a + 1, len(aligned)):
            aligned[i]["start"] = round(cur_t, 3)
            aligned[i]["end"] = round(cur_t + 0.30, 3)
            cur_t += 0.30

        # Enforce strict monotonicity guarantee
        for i in range(len(aligned) - 1):
            cur = aligned[i]
            nxt = aligned[i + 1]

            if cur["end"] <= cur["start"]:
                cur["end"] = round(cur["start"] + 0.08, 3)

            if nxt["start"] < cur["end"]:
                nxt["start"] = round(cur["end"] + 0.01, 3)
                if nxt["end"] <= nxt["start"]:
                    nxt["end"] = round(nxt["start"] + 0.12, 3)

        if aligned:
            last = aligned[-1]
            if last["end"] <= last["start"]:
                last["end"] = round(last["start"] + 0.15, 3)

        return aligned

    def build_segments_from_words(self, aligned_words: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Groups aligned words into structured segments split by natural speech pauses (> 0.55s).
        """
        if not aligned_words:
            return []

        segments: List[Dict[str, Any]] = []
        cur_words: List[Dict[str, Any]] = []

        def flush():
            nonlocal cur_words
            if not cur_words:
                return

            text = " ".join(w["word"] for w in cur_words).strip()
            if not text:
                cur_words = []
                return

            start = float(cur_words[0]["start"])
            end = float(cur_words[-1]["end"])
            avg_prob = sum(w.get("probability", 1.0) for w in cur_words) / len(cur_words)

            segments.append({
                "index": len(segments),
                "start": round(start, 3),
                "end": round(max(end, start + 0.3), 3),
                "text": text,
                "confidence": int(avg_prob * 100),
                "speaker": "Speaker 1",
                "words": [
                    {
                        "word": w["word"],
                        "start": round(w["start"], 3),
                        "end": round(w["end"], 3),
                        "probability": round(w.get("probability", 1.0), 3)
                    }
                    for w in cur_words
                ]
            })
            cur_words = []

        for w in aligned_words:
            if not w["word"].strip():
                continue

            if cur_words:
                pause = w["start"] - cur_words[-1]["end"]
                prev_w = cur_words[-1]["word"].strip()
                has_sentence_end = bool(re.search(r"[.!?\u3002\uff1f\uff01][\"'\u201d\u2019)]*$", prev_w))
                # Split segment if silence between words is >= 0.55s OR previous word ended a sentence!
                if pause >= 0.55 or has_sentence_end:
                    flush()

            cur_words.append(w)

        flush()
        return segments
