"""
Subtitle Maker — Professional Subtitle Alignment Engine
Standards: Netflix Timed Text, BBC Subtitle Guidelines, and Social Media (TikTok/Reels/Shorts)
Handles charLimit enforcement, Indonesian conjunction line breaks, CPS scoring, and strict gap constraints.
"""

import re
from typing import List, Dict, Any, Optional

# Indonesian conjunctions for natural subtitle break points
CONJUNCTIONS = {
    "dan", "atau", "tetapi", "tapi", "karena", "namun", "sehingga",
    "yang", "untuk", "dengan", "dari", "pada", "oleh", "ke", "di",
    "jadi", "maka", "agar", "supaya", "kalau", "jika", "bila",
    "walaupun", "meskipun", "sedangkan", "kemudian", "lalu", "lagi"
}

STRONG_BREAK_RE = re.compile(r"[.!?\u3002\uff1f\uff01][\"'\u201d\u2019)]*$")
MEDIUM_BREAK_RE = re.compile(r"[,;:\uff0c\uff1b]")

ALIGN_RULES = {
    "MAX_CHARS_PER_LINE": 42,
    "MAX_LINES": 2,
    "MAX_CUE_DURATION": 6.0,
    "MIN_CUE_DURATION": 0.8,
    "MIN_GAP": 0.083,  # 2-3 frames @ 24/30fps
    "TARGET_CPS_MIN": 12,
    "TARGET_CPS_MAX": 22,
    "IDEAL_CPS": 17,
}


class SubtitleCue:
    def __init__(
        self,
        index: int,
        start: float,
        end: float,
        text: str,
        lines: List[str],
        confidence: int = 100,
        speaker: str = "Speaker 1"
    ):
        self.index = index
        self.start = round(start, 3)
        self.end = round(end, 3)
        self.text = text.strip()
        self.lines = lines
        self.duration = round(max(0.05, self.end - self.start), 3)
        self.cps = round(len(self.text) / self.duration, 1) if self.duration > 0 else 0.0
        self.confidence = confidence
        self.speaker = speaker

    def to_dict(self) -> Dict[str, Any]:
        return {
            "index": self.index,
            "start": self.start,
            "end": self.end,
            "duration": self.duration,
            "text": self.text,
            "lines": self.lines,
            "cps": self.cps,
            "confidence": self.confidence,
            "speaker": self.speaker
        }


class AlignmentEngine:
    def __init__(self):
        pass

    def smart_line_break(self, text: str, max_chars: int = 42) -> List[str]:
        """
        Split a subtitle into 1 or 2 lines naturally.
        Prefers breaking at conjunctions, commas, or balanced half points.
        """
        text = text.strip()
        if len(text) <= max_chars:
            return [text]

        words = text.split()
        if len(words) <= 1:
            return [text]

        best_split_idx = -1
        best_balance_diff = float("inf")
        half_len = len(text) / 2

        cur_len = 0
        for i in range(len(words) - 1):
            cur_len += len(words[i]) + (1 if i > 0 else 0)
            next_word = words[i + 1].lower()

            diff = abs(cur_len - half_len)

            # Bonus if next word is a conjunction
            if next_word in CONJUNCTIONS:
                diff -= 8

            # Bonus if current word ends with punctuation
            if MEDIUM_BREAK_RE.search(words[i][-1:]):
                diff -= 10

            if diff < best_balance_diff and cur_len <= max_chars and (len(text) - cur_len) <= max_chars:
                best_balance_diff = diff
                best_split_idx = i

        if best_split_idx != -1:
            line1 = " ".join(words[:best_split_idx + 1])
            line2 = " ".join(words[best_split_idx + 1:])
            return [line1, line2]

        # Fallback simple middle split
        mid = len(words) // 2
        return [" ".join(words[:mid]), " ".join(words[mid:])]

    def build_cues_from_words(
        self,
        words: List[Dict[str, Any]],
        char_limit: Optional[int] = None
    ) -> List[SubtitleCue]:
        cues: List[SubtitleCue] = []
        is_single_line = bool(char_limit and char_limit > 0)
        max_chars = char_limit if is_single_line else (ALIGN_RULES["MAX_CHARS_PER_LINE"] * ALIGN_RULES["MAX_LINES"])

        cur_words: List[Dict[str, Any]] = []

        def flush_cue():
            nonlocal cur_words
            if not cur_words:
                return

            txt = " ".join(w["word"] for w in cur_words).strip()
            # Clean accidental leading/trailing punctuation or stray dashes
            txt = re.sub(r"^[\s\-\u2013\u2014]+", "", txt)
            txt = re.sub(r"[\s\-\u2013\u2014]+$", "", txt)
            if not txt:
                cur_words = []
                return

            start = float(cur_words[0]["start"])
            raw_end = float(cur_words[-1]["end"])

            # Duration calculation
            min_dur = 0.5 if is_single_line else 0.8
            end = max(raw_end, round(start + min_dur, 3))
            end = min(end, round(start + ALIGN_RULES["MAX_CUE_DURATION"], 3))

            avg_conf = int(sum(w.get("probability", 1.0) for w in cur_words) / len(cur_words) * 100)
            speaker = cur_words[0].get("speaker", "Speaker 1")

            lines = [txt] if is_single_line else self.smart_line_break(txt, max_chars=ALIGN_RULES["MAX_CHARS_PER_LINE"])

            cues.append(SubtitleCue(
                index=len(cues) + 1,
                start=start,
                end=end,
                text=txt,
                lines=lines,
                confidence=avg_conf,
                speaker=speaker
            ))

            cur_words = []

        for w in words:
            word_str = w["word"].strip()
            if not word_str:
                continue

            cur_text = " ".join(cw["word"] for cw in cur_words) if cur_words else ""
            candidate_text = f"{cur_text} {word_str}".strip() if cur_text else word_str
            start_time = float(w["start"])
            end_time = float(w["end"])

            would_exceed_chars = len(candidate_text) > max_chars
            would_exceed_duration = cur_words and (end_time - float(cur_words[0]["start"])) > ALIGN_RULES["MAX_CUE_DURATION"]

            # Pause detection between words (> 0.55s is a distinct speech pause)
            prev_end = float(cur_words[-1]["end"]) if cur_words else 0.0
            has_pause = cur_words and (start_time - prev_end) >= 0.55

            # Grammatical break checks
            prev_word = cur_words[-1]["word"] if cur_words else ""
            has_strong_break = bool(STRONG_BREAK_RE.search(prev_word.strip())) if prev_word else False
            has_medium_break = bool(MEDIUM_BREAK_RE.search(prev_word[-1:])) if prev_word else False
            is_conjunction = word_str.lower() in CONJUNCTIONS

            should_flush = False
            # 1. HARD RULE: NEVER combine different sentences into the same subtitle cue!
            # If the previous word ended a sentence (. ! ?), flush immediately so the new sentence starts fresh.
            if has_strong_break:
                should_flush = True
            elif has_pause:
                should_flush = True
            elif would_exceed_chars:
                should_flush = True
            elif would_exceed_duration:
                should_flush = True
            elif has_medium_break and len(cur_text) >= 24:
                should_flush = True
            elif is_conjunction and len(cur_text) >= 28:
                should_flush = True

            if should_flush:
                flush_cue()

            cur_words.append(w)

        flush_cue()
        return cues

    def enforce_gaps(self, cues: List[SubtitleCue]) -> List[SubtitleCue]:
        """
        Guarantees:
        1. Strictly ascending chronological order.
        2. Zero overlapping cues (non-overlapping).
        3. Minimum gap between cues.
        """
        if not cues:
            return []

        # 1. Strictly sort by start timestamp
        cues.sort(key=lambda c: c.start)
        min_gap = ALIGN_RULES["MIN_GAP"]

        for i in range(len(cues) - 1):
            cur = cues[i]
            nxt = cues[i + 1]

            if cur.end <= cur.start:
                cur.end = round(cur.start + 0.3, 3)

            # Prevent overlap
            if cur.end >= nxt.start:
                cur.end = round(max(cur.start + 0.3, nxt.start - min_gap), 3)

                # If next starts before or equal to current end
                if nxt.start <= cur.end:
                    nxt.start = round(cur.end + min_gap, 3)
                    if nxt.end <= nxt.start:
                        nxt.end = round(nxt.start + 0.4, 3)

            # If cue is very short and there is space before nxt.start, extend cur.end slightly for readability!
            if (cur.end - cur.start) < 0.8 and (nxt.start - cur.end) > min_gap:
                max_extend = min(0.8, nxt.start - min_gap - cur.start)
                if max_extend > (cur.end - cur.start):
                    cur.end = round(cur.start + max_extend, 3)

            cur.duration = round(max(0.1, cur.end - cur.start), 3)
            cur.cps = round(len(cur.text) / cur.duration, 1)

        if cues:
            last = cues[-1]
            if last.end <= last.start:
                last.end = round(last.start + 0.4, 3)
            last.duration = round(max(0.1, last.end - last.start), 3)
            last.cps = round(len(last.text) / last.duration, 1)

        for idx, c in enumerate(cues):
            c.index = idx + 1

        return cues

    def merge_tiny_cues(self, cues: List[SubtitleCue], char_limit: Optional[int] = None) -> List[SubtitleCue]:
        """
        Merge very short flickers (<0.6s or single short word) with adjacent cue.
        CRITICAL: NEVER merge across sentence boundaries (. ! ?).
        """
        if len(cues) <= 1:
            return cues

        max_chars = char_limit if char_limit else (ALIGN_RULES["MAX_CHARS_PER_LINE"] * ALIGN_RULES["MAX_LINES"])
        merged: List[SubtitleCue] = []
        i = 0

        while i < len(cues):
            cur = cues[i]
            # Check if cur ends a sentence
            cur_ends_sentence = bool(STRONG_BREAK_RE.search(cur.text.strip()))

            # ONLY merge within the same sentence! NEVER merge across sentence boundaries!
            if not cur_ends_sentence and cur.duration < 0.6 and (i + 1) < len(cues):
                nxt = cues[i + 1]
                comb_text = f"{cur.text} {nxt.text}"
                comb_dur = nxt.end - cur.start
                if len(comb_text) <= max_chars and comb_dur <= ALIGN_RULES["MAX_CUE_DURATION"]:
                    lines = [comb_text] if char_limit else self.smart_line_break(comb_text)
                    merged.append(SubtitleCue(
                        index=len(merged) + 1,
                        start=cur.start,
                        end=nxt.end,
                        text=comb_text,
                        lines=lines,
                        confidence=min(cur.confidence, nxt.confidence),
                        speaker=cur.speaker
                    ))
                    i += 2
                    continue

            merged.append(cur)
            i += 1

        return merged

    def align(
        self,
        segments: List[Dict[str, Any]],
        char_limit: Optional[int] = None
    ) -> List[SubtitleCue]:
        """
        Main entry point for alignment and cue structuring.
        """
        all_words: List[Dict[str, Any]] = []
        for s in segments:
            speaker = s.get("speaker", "Speaker 1")
            if "words" in s and s["words"]:
                for w in s["words"]:
                    w_copy = dict(w)
                    w_copy["speaker"] = speaker
                    all_words.append(w_copy)
            else:
                words_list = s.get("text", "").split()
                if not words_list:
                    continue
                seg_dur = max(0.5, float(s.get("end", 1.0)) - float(s.get("start", 0.0)))
                w_dur = seg_dur / len(words_list)
                start = float(s.get("start", 0.0))
                for j, w_str in enumerate(words_list):
                    all_words.append({
                        "word": w_str,
                        "start": round(start + j * w_dur, 3),
                        "end": round(start + (j + 1) * w_dur, 3),
                        "probability": 1.0,
                        "speaker": speaker
                    })

        if not all_words:
            return []

        cues = self.build_cues_from_words(all_words, char_limit=char_limit)
        cues = self.enforce_gaps(cues)
        cues = self.merge_tiny_cues(cues, char_limit=char_limit)
        cues = self.enforce_gaps(cues)  # Re-enforce strictly after merge
        return cues
