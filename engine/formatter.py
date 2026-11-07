"""
Subtitle Maker — Subtitle Formatter Module
Generates UTF-8 safe SRT (with BOM option), VTT, ASS (styled with speaker colors), and TXT files.
"""

import os
from typing import List
from .rules import SubtitleCue


def format_srt_time(seconds: float) -> str:
    """Format seconds into SRT timestamp: HH:MM:SS,mmm"""
    sec = max(0.0, seconds)
    hrs = int(sec // 3600)
    mins = int((sec % 3600) // 60)
    secs = int(sec % 60)
    ms = int(round((sec % 1) * 1000))
    if ms >= 1000:
        ms = 999
    return f"{hrs:02d}:{mins:02d}:{secs:02d},{ms:03d}"


def format_vtt_time(seconds: float) -> str:
    """Format seconds into WebVTT timestamp: HH:MM:SS.mmm"""
    return format_srt_time(seconds).replace(",", ".")


def format_ass_time(seconds: float) -> str:
    """Format seconds into ASS timestamp: H:MM:SS.cc (centiseconds)"""
    sec = max(0.0, seconds)
    hrs = int(sec // 3600)
    mins = int((sec % 3600) // 60)
    secs = int(sec % 60)
    cs = int(round((sec % 1) * 100))
    if cs >= 100:
        cs = 99
    return f"{hrs}:{mins:02d}:{secs:02d}.{cs:02d}"


def to_srt(cues: List[SubtitleCue]) -> str:
    """Compose standard SRT content."""
    lines = []
    for i, cue in enumerate(cues):
        if not cue.text.strip():
            continue
        lines.append(str(i + 1))
        lines.append(f"{format_srt_time(cue.start)} --> {format_srt_time(cue.end)}")
        lines.append("\n".join(cue.lines) if cue.lines else cue.text)
        lines.append("")
    return "\n".join(lines)


def to_vtt(cues: List[SubtitleCue]) -> str:
    """Compose WebVTT content."""
    lines = ["WEBVTT", ""]
    for i, cue in enumerate(cues):
        if not cue.text.strip():
            continue
        lines.append(str(i + 1))
        lines.append(f"{format_vtt_time(cue.start)} --> {format_vtt_time(cue.end)}")
        lines.append("\n".join(cue.lines) if cue.lines else cue.text)
        lines.append("")
    return "\n".join(lines)


def to_txt(cues: List[SubtitleCue]) -> str:
    """Compose plain text transcript with timestamps."""
    lines = []
    for cue in cues:
        if not cue.text.strip():
            continue
        time_str = f"[{format_srt_time(cue.start).split(',')[0]}]"
        lines.append(f"{time_str} {cue.text}")
    return "\n".join(lines)


def to_ass(cues: List[SubtitleCue], language: str = "id", title: str = "Subtitle Maker") -> str:
    """
    Compose styled Advanced SubStation Alpha (.ass) with professional styles.
    Supports distinct speaker colors and Arabic / CJK typography.
    """
    font_name = "Outfit, Arial, sans-serif"
    is_rtl = False

    if language in ["ja", "japanese"]:
        font_name = "Noto Sans JP, Arial"
    elif language in ["ko", "korean"]:
        font_name = "Noto Sans KR, Arial"
    elif language in ["zh", "chinese"]:
        font_name = "Noto Sans SC, Arial"
    elif language in ["ar", "arabic"]:
        font_name = "Noto Sans Arabic, Arial"
        is_rtl = True

    header = f"""[Script Info]
Title: {title}
ScriptType: v4.00+
WrapStyle: 0
PlayResX: 1920
PlayResY: 1080
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{font_name},52,&H00FFFFFF,&H000000FF,&H00000000,&H90000000,-1,0,0,0,100,100,0,0,1,3.5,2,2,40,40,60,1
Style: Speaker1,{font_name},52,&H00C5FFC5,&H000000FF,&H00000000,&H90000000,-1,0,0,0,100,100,0,0,1,3.5,2,2,40,40,60,1
Style: Speaker2,{font_name},52,&H00C5E9FF,&H000000FF,&H00000000,&H90000000,-1,0,0,0,100,100,0,0,1,3.5,2,2,40,40,60,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    events = []
    for cue in cues:
        if not cue.text.strip():
            continue
        start_str = format_ass_time(cue.start)
        end_str = format_ass_time(cue.end)
        style = "Default"
        if cue.speaker == "Speaker 1":
            style = "Speaker1"
        elif cue.speaker == "Speaker 2":
            style = "Speaker2"

        # Escape ASS markup characters
        clean_text = cue.text.replace("{", "\\{").replace("}", "\\}")
        if cue.lines and len(cue.lines) > 1:
            clean_text = "\\N".join(l.replace("{", "\\{").replace("}", "\\}") for l in cue.lines)

        if is_rtl:
            clean_text = "\u200F" + clean_text

        events.append(f"Dialogue: 0,{start_str},{end_str},{style},,0,0,0,,{clean_text}")

    return header + "\n".join(events) + "\n"


def write_file(file_path: str, content: str, add_bom: bool = True):
    """Write text file with UTF-8 encoding (and optional BOM)."""
    os.makedirs(os.path.dirname(os.path.abspath(file_path)), exist_ok=True)
    bom = "\ufeff" if add_bom else ""
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(bom + content)
