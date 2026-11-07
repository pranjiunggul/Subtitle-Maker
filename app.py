"""
Subtitle Maker — Standalone Lightweight Application
Main Entry Point (Web Server & CLI)
Lightweight speech-to-text subtitle generator optimized for 4GB RAM laptops.
"""

import os
import sys
import json
import uuid
import time
import argparse
import threading
import webbrowser
from typing import Dict, Any

from bottle import Bottle, request, response, static_file, run

# Add parent directory to sys.path
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

# Fix Windows console UTF-8 encoding
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

from engine.audio import check_ffmpeg
from engine.transcriber import SubtitlePipeline, get_model_cache_dir
from engine.rules import SubtitleCue
from engine.formatter import to_srt, to_vtt, to_ass, to_txt, write_file
from engine.vocabulary import VocabularyManager

# Storage paths
TEMP_DIR = os.path.join(BASE_DIR, "temp")
OUTPUT_DIR = os.path.join(BASE_DIR, "output")
WEB_DIR = os.path.join(BASE_DIR, "web")
os.makedirs(TEMP_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(WEB_DIR, exist_ok=True)

# Shared Pipeline & Jobs
pipeline = SubtitlePipeline()
vocab_mgr = VocabularyManager()
active_jobs: Dict[str, Dict[str, Any]] = {}

app = Bottle()


# ── CORS Middleware ──
@app.hook('after_request')
def enable_cors():
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS'
    response.headers['Access-Control-Allow-Headers'] = 'Origin, Accept, Content-Type, X-Requested-With'


# ── Root / UI Entry Point ──
@app.route('/')
def serve_index():
    return static_file('index.html', root=WEB_DIR)


# ── System Health & Status ──
@app.route('/api/status', method=['GET'])
def get_status():
    ffmpeg_info = check_ffmpeg()
    return {
        "status": "ready",
        "ffmpeg": ffmpeg_info,
        "model_cache": pipeline.model_cache_dir,
        "models_available": ["base (Rekomendasi 4GB)", "small", "tiny"],
        "default_model": pipeline.current_model_size or "base",
        "temp_dir": TEMP_DIR,
        "output_dir": OUTPUT_DIR
    }


# ── Recent Completed Subtitles ──
@app.route('/api/recent', method=['GET'])
def get_recent():
    results = []
    if os.path.isdir(OUTPUT_DIR):
        files = [f for f in os.listdir(OUTPUT_DIR) if f.endswith(".meta.json")]
        files.sort(key=lambda f: os.path.getmtime(os.path.join(OUTPUT_DIR, f)), reverse=True)
        for f in files[:5]:
            try:
                with open(os.path.join(OUTPUT_DIR, f), "r", encoding="utf-8") as fp:
                    data = json.load(fp)
                    results.append({
                        "id": data.get("id"),
                        "filename": data.get("filename"),
                        "language": data.get("language"),
                        "duration": data.get("result", {}).get("duration", 0),
                        "cues_count": data.get("result", {}).get("cues_count", 0)
                    })
            except Exception:
                continue
    return {"items": results}


# ── Vocabulary / Pronunciation Rules ──
@app.route('/api/vocabulary', method=['GET'])
def get_vocabulary():
    return {"rules": vocab_mgr.list_rules()}


@app.route('/api/vocabulary', method=['POST'])
def add_vocabulary():
    data = request.json or {}
    raw = data.get("raw", "")
    corrected = data.get("corrected", "")
    domain = data.get("domain", "general")
    if vocab_mgr.add_rule(raw, corrected, domain):
        return {"success": True, "rules": vocab_mgr.list_rules()}
    response.status = 400
    return {"error": "Invalid rule data"}


@app.route('/api/vocabulary/<index:int>', method=['DELETE'])
def delete_vocabulary(index):
    if vocab_mgr.delete_rule(index):
        return {"success": True, "rules": vocab_mgr.list_rules()}
    response.status = 400
    return {"error": "Failed to delete rule"}


# ── Transcription Endpoint ──
@app.route('/api/transcribe', method=['POST'])
def transcribe_media():
    upload = request.files.get('file')
    if not upload:
        response.status = 400
        return {"error": "No file uploaded"}

    language = request.forms.get('language', 'auto')
    model = request.forms.get('model', 'auto')
    narration = request.forms.get('narration', '')
    char_limit_str = request.forms.get('charLimit', '')
    denoise = request.forms.get('denoise', 'true').lower() == 'true'

    char_limit = None
    if char_limit_str and char_limit_str.strip():
        try:
            val = int(char_limit_str.strip())
            if val > 0:
                char_limit = val
        except ValueError:
            pass

    job_id = str(uuid.uuid4())
    safe_filename = upload.raw_filename.replace(" ", "_")
    saved_path = os.path.join(TEMP_DIR, f"{job_id}_{safe_filename}")
    upload.save(saved_path)

    active_jobs[job_id] = {
        "id": job_id,
        "status": "queued",
        "progress": 0,
        "message": "Initializing...",
        "filename": safe_filename,
        "filepath": saved_path,
        "language": language,
        "model": model,
        "char_limit": char_limit,
        "narration": narration,
        "result": None,
        "error": None
    }

    def run_worker():
        job = active_jobs[job_id]
        job["status"] = "processing"

        def on_prog(percent: int, msg: str):
            job["progress"] = percent
            job["message"] = msg

        try:
            res = pipeline.process(
                input_path=saved_path,
                language=language,
                model_size=model,
                narration_text=narration,
                char_limit=char_limit,
                on_progress=on_prog
            )
            # Pre-generate subtitle files in output directory
            cues_objs = [
                SubtitleCue(
                    c["index"], c["start"], c["end"], c["text"],
                    c.get("lines", [c["text"]]), c.get("confidence", 100), c.get("speaker", "Speaker 1")
                )
                for c in res["cues"]
            ]
            base_out = os.path.join(OUTPUT_DIR, f"{job_id}_{os.path.splitext(safe_filename)[0]}")
            write_file(f"{base_out}.srt", to_srt(cues_objs))
            write_file(f"{base_out}.vtt", to_vtt(cues_objs), add_bom=False)
            write_file(f"{base_out}.ass", to_ass(cues_objs, language=res.get("language", "id")))
            write_file(f"{base_out}.txt", to_txt(cues_objs), add_bom=False)

            res["output_base"] = base_out
            job["status"] = "completed"
            job["progress"] = 100
            job["message"] = "Completed successfully!"
            job["result"] = res

            # Save metadata for session restore / persistence
            meta_path = f"{base_out}.meta.json"
            try:
                with open(meta_path, "w", encoding="utf-8") as f:
                    json.dump({
                        "id": job_id,
                        "filename": safe_filename,
                        "filepath": saved_path,
                        "language": language,
                        "model": model,
                        "result": res
                    }, f, ensure_ascii=False, indent=2)
            except Exception:
                pass
        except Exception as e:
            job["status"] = "failed"
            job["message"] = f"Error: {str(e)}"
            job["error"] = str(e)

    # Launch background thread
    t = threading.Thread(target=run_worker, daemon=True)
    t.start()

    return {"jobId": job_id, "status": "queued"}


# ── Progress Polling ──
@app.route('/api/progress/<job_id>', method=['GET'])
def get_job_progress(job_id):
    job = active_jobs.get(job_id)
    if not job:
        # Check if saved meta exists on disk (e.g. after server restart)
        candidates = [f for f in os.listdir(OUTPUT_DIR) if f.startswith(f"{job_id}_") and f.endswith(".meta.json")]
        if candidates:
            try:
                with open(os.path.join(OUTPUT_DIR, candidates[0]), "r", encoding="utf-8") as f:
                    meta = json.load(f)
                return {
                    "jobId": meta["id"],
                    "status": "completed",
                    "progress": 100,
                    "message": "Completed successfully!",
                    "result": meta.get("result"),
                    "error": None
                }
            except Exception:
                pass
        response.status = 404
        return {"error": "Job not found"}
    return {
        "jobId": job["id"],
        "status": job["status"],
        "progress": job["progress"],
        "message": job["message"],
        "result": job.get("result"),
        "error": job.get("error")
    }


# ── Download Subtitles ──
@app.route('/api/download/<job_id>/<fmt>', method=['GET'])
def download_subtitle(job_id, fmt):
    ext = f".{fmt.lower()}"
    job = active_jobs.get(job_id)

    if job and job.get("status") == "completed":
        result = job.get("result", {})
        output_base = result.get("output_base")
        if output_base:
            file_path = f"{output_base}{ext}"
            if os.path.isfile(file_path):
                orig_name = os.path.splitext(job["filename"])[0]
                return static_file(
                    os.path.basename(file_path),
                    root=OUTPUT_DIR,
                    download=f"{orig_name}{ext}"
                )

    # Fallback: check OUTPUT_DIR on disk
    candidates = [f for f in os.listdir(OUTPUT_DIR) if f.startswith(f"{job_id}_") and f.endswith(ext)]
    if candidates:
        filename = candidates[0]
        clean_name = filename[len(job_id) + 1:]
        return static_file(filename, root=OUTPUT_DIR, download=clean_name)

    response.status = 404
    return {"error": f"Subtitle not ready or format {fmt} not found"}


# ── Serve Uploaded Media for Live Browser Player ──
@app.route('/api/media/<job_id>', method=['GET'])
def stream_media(job_id):
    job = active_jobs.get(job_id)
    if job and "filepath" in job and os.path.isfile(job["filepath"]):
        return static_file(
            os.path.basename(job["filepath"]),
            root=TEMP_DIR
        )

    # Fallback: check TEMP_DIR on disk
    candidates = [f for f in os.listdir(TEMP_DIR) if f.startswith(f"{job_id}_")]
    if candidates:
        return static_file(candidates[0], root=TEMP_DIR)

    response.status = 404
    return {"error": "Media not found"}


# ── Live Export Updated Cues ──
@app.route('/api/export', method=['POST'])
def export_cues():
    """Export modified cues directly from the editor."""
    data = request.json or {}
    cues_data = data.get("cues", [])
    fmt = data.get("format", "srt").lower()
    lang = data.get("language", "id")

    cues_objs = [
        SubtitleCue(
            c.get("index", i),
            float(c["start"]),
            float(c["end"]),
            c["text"],
            c.get("lines", [c["text"]]),
            int(c.get("confidence", 100)),
            c.get("speaker", "Speaker 1")
        )
        for i, c in enumerate(cues_data)
    ]

    if fmt == "srt":
        content = to_srt(cues_objs)
        mime = "application/x-subrip"
    elif fmt == "vtt":
        content = to_vtt(cues_objs)
        mime = "text/vtt"
    elif fmt == "ass":
        content = to_ass(cues_objs, language=lang)
        mime = "text/x-ssa"
    else:
        content = to_txt(cues_objs)
        mime = "text/plain"

    response.content_type = f"{mime}; charset=utf-8"
    return content


# ── Static Files Fallback (Must be declared AFTER all API routes) ──
@app.route('/<filepath:path>')
def serve_static(filepath):
    if filepath.startswith('api/'):
        response.status = 404
        return {"error": "API route not found"}
    return static_file(filepath, root=WEB_DIR)


# ── CLI Mode Execution ──
def run_cli_mode(args):
    print("=" * 60)
    print("🧠 Subtitle Maker — CLI Mode")
    print("=" * 60)

    input_file = args.input
    if not os.path.isfile(input_file):
        print(f"Error: File '{input_file}' not found.")
        sys.exit(1)

    narration = ""
    if args.narration and os.path.isfile(args.narration):
        with open(args.narration, "r", encoding="utf-8") as f:
            narration = f.read()

    def cli_progress(percent: int, msg: str):
        print(f"[{percent:3d}%] {msg}")

    print(f"File: {input_file}")
    print(f"Model: {args.model}")
    print(f"Language: {args.language}")
    print(f"Char Limit: {args.char_limit or 'Auto (Netflix standard)'}")
    if narration:
        print(f"Narration: {len(narration)} chars (Forced Alignment ENABLED)")

    res = pipeline.process(
        input_path=input_file,
        language=args.language,
        model_size=args.model,
        narration_text=narration,
        char_limit=args.char_limit,
        on_progress=cli_progress
    )

    cues_objs = [
        SubtitleCue(
            c["index"], c["start"], c["end"], c["text"],
            c.get("lines", [c["text"]]), c.get("confidence", 100), c.get("speaker", "Speaker 1")
        )
        for c in res["cues"]
    ]

    base_out = args.output or os.path.splitext(input_file)[0]
    write_file(f"{base_out}.srt", to_srt(cues_objs))
    write_file(f"{base_out}.vtt", to_vtt(cues_objs), add_bom=False)
    write_file(f"{base_out}.ass", to_ass(cues_objs, language=res.get("language", "id")))
    write_file(f"{base_out}.txt", to_txt(cues_objs), add_bom=False)

    print("=" * 60)
    print("✅ Completed! Subtitles saved to:")
    print(f" - {base_out}.srt")
    print(f" - {base_out}.vtt")
    print(f" - {base_out}.ass")
    print(f" - {base_out}.txt")
    print(f"Total Cues: {len(cues_objs)}")
    print("=" * 60)


def main():
    parser = argparse.ArgumentParser(description="Subtitle Maker — Lightweight Subtitle Generator")
    parser.add_argument("--cli", action="store_true", help="Run in CLI mode instead of web server")
    parser.add_argument("--input", "-i", type=str, help="Media input file (for CLI mode)")
    parser.add_argument("--narration", "-n", type=str, help="Narration script text file (optional for CLI)")
    parser.add_argument("--language", "-l", type=str, default="auto", help="Language code (id, en, auto, etc.)")
    parser.add_argument("--model", "-m", type=str, default="auto", help="Whisper model (auto, tiny, base, small, medium, large-v3)")
    parser.add_argument("--char-limit", "-c", type=int, default=None, help="Character limit per line (e.g. 30 for Reels/Shorts)")
    parser.add_argument("--output", "-o", type=str, default=None, help="Output base filename")
    parser.add_argument("--port", "-p", type=int, default=5050, help="Web server port (default: 5050)")
    parser.add_argument("--no-browser", action="store_true", help="Do not open browser automatically")

    args = parser.parse_args()

    if args.cli:
        if not args.input:
            print("Error: --input is required in CLI mode.")
            sys.exit(1)
        run_cli_mode(args)
    else:
        port = args.port
        url = f"http://localhost:{port}"

        print("=" * 60)
        print("🧠 Subtitle Maker — Lightweight Standalone Edition (4GB RAM Ready)")
        print(f"🌐 Server running at: {url}")
        print("=" * 60)

        if not args.no_browser:
            def open_browser():
                time.sleep(1.0)
                webbrowser.open(url)
            threading.Thread(target=open_browser, daemon=True).start()

        run(app, host='0.0.0.0', port=port, server='wsgiref', quiet=False)


if __name__ == '__main__':
    main()
