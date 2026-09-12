---
name: transcribe
description: Transcribe audio or video to a text transcript, locally and privately (no cloud, no API keys). Handles a URL (Loom, YouTube, Google Drive, podcast) or a local media file. Use whenever the user wants to transcribe, get a transcript of, or "what was said in" a video or audio file or link, including interview, meeting, or work-sample recordings.
---

# Transcribe media to text

**Requires macOS on Apple Silicon** (the MLX engines do not run on Intel Macs or other platforms; the script checks and exits early if not).

Local transcription via MLX. Default engine is `parakeet-mlx` (model `mlx-community/parakeet-tdt-0.6b-v3`, chunks long audio automatically). `--model whisper` switches to `mlx-whisper`, which supports `--language` and broader language coverage.

## Usage

Run the `transcribe.py` next to this SKILL.md (it self-installs its Python deps on first run via `uv`). Use the copy adjacent to the active SKILL.md:

```bash
uv run "<skill-dir>/transcribe.py" <url-or-file> [options]
```

Replace `<skill-dir>` with the absolute directory containing the loaded SKILL.md. Keep the caller's cwd for output placement; do not change into the installed skill directory.

If you symlinked the script onto your PATH, `transcribe <url-or-file>` works as a shorthand. The script needs `uv` and `ffmpeg`/`ffprobe`; the Drive fallback uses `curl` and the engines run via `uvx` (both come with a standard uv + ffmpeg setup).

Common options: `--model {parakeet|whisper|<hf-id>}`, `--format {txt|srt|vtt|json}` (default txt), `--output-dir DIR` (default cwd), `--language CODE` (whisper only), `--keep-media`, `--drive-direct` (force direct Google Drive download if yt-dlp fails), `--force`, `--quiet`/`--verbose`. Run with `--help` for the full list.

## Behavior

- The transcript file path is printed to stdout; all progress and errors go to stderr. Capture stdout to get the path.
- Source is auto-detected: local file, Google Drive link, or any yt-dlp-supported URL.
- After running, tell the user the output path and the engine used. For long videos, note that transcription ran locally (private).

## Notes

- First run fetches the engine package and model, then caches them (the default Parakeet model is ~600MB; whisper or custom models download separately). Transcription is on-device; only the source URL and, on first run, PyPI and Hugging Face are contacted.
- Failures exit with a clear message: no-audio video, private or view-only Drive link, malformed URL, missing ffmpeg. Relay the message instead of retrying blindly.
- Parakeet ignores `--language` (it auto-detects); to force a language, use `--model whisper --language <code>`.
- Scoring or analysis (e.g. against a hiring rubric) is out of scope. This only produces transcripts.
