#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "typer>=0.12",
#     "yt-dlp>=2025.1.1",
# ]
# ///
# Note: the MLX engines (parakeet-mlx, mlx-whisper) are run lazily via `uvx`,
# not declared here, so this script starts on any platform and the Apple Silicon
# guard can fail with a friendly message before any MLX resolution is attempted.
"""Transcribe any audio/video (URL or local file) to text, locally.

Source -> download (temp dir) -> 16k mono wav -> transcribe -> write transcript.
Default engine is NVIDIA Parakeet v3 (MLX); --model whisper switches to the
mlx-whisper fallback. No cloud, no API keys.

System prerequisites (checked at startup): ffmpeg, ffprobe. curl is used only as
a fallback for large Google Drive files.

stdout = the path to the written transcript (one line). All logs go to stderr.
"""

from __future__ import annotations

import platform
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Optional

import typer

app = typer.Typer(add_completion=False)

PARAKEET_MODEL = "mlx-community/parakeet-tdt-0.6b-v3"
WHISPER_MODEL = "mlx-community/whisper-large-v3-turbo"
FORMATS = ("txt", "srt", "vtt", "json")
MEDIA_EXTS = {
    "mp4", "mkv", "mov", "webm", "avi", "flv", "m4v", "mpg", "mpeg", "wmv",
    "mp3", "m4a", "wav", "flac", "ogg", "opus", "aac", "wma", "aiff",
}


class AcquisitionError(Exception):
    """A download failed in a way the caller may recover from (e.g. fallback)."""

# module-level verbosity, set in main()
_QUIET = False
_VERBOSE = False


def log(msg: str) -> None:
    """Phase/status message to stderr (suppressed in --quiet)."""
    if not _QUIET:
        print(msg, file=sys.stderr, flush=True)


def warn(msg: str) -> None:
    """Warning to stderr (always shown)."""
    print(f"warning: {msg}", file=sys.stderr, flush=True)


def die(msg: str, code: int = 1) -> "NoReturn":  # type: ignore[name-defined]
    print(f"error: {msg}", file=sys.stderr, flush=True)
    raise typer.Exit(code)


def is_interactive() -> bool:
    return sys.stderr.isatty()


# --------------------------------------------------------------------------- #
# prerequisites
# --------------------------------------------------------------------------- #
def is_apple_silicon() -> bool:
    """True on Apple Silicon macOS, seen through Rosetta.

    Under Rosetta 2 `platform.machine()` reports x86_64, so we ask the kernel
    directly. Intel Macs return a non-zero exit ('unknown oid'), not "0", so any
    error or non-"1" output means not Apple Silicon.
    """
    if platform.system() != "Darwin":
        return False
    try:
        cp = subprocess.run(
            ["sysctl", "-n", "hw.optional.arm64"], capture_output=True, text=True
        )
    except OSError:
        return False
    return cp.returncode == 0 and cp.stdout.strip() == "1"


def check_platform() -> None:
    if not is_apple_silicon():
        die(
            f"requires macOS on Apple Silicon (the MLX engines do not run on "
            f"{platform.system()}/{platform.machine()}). See the README."
        )


def check_prereqs() -> None:
    missing = [t for t in ("ffmpeg", "ffprobe") if shutil.which(t) is None]
    if missing:
        die(
            f"missing required tool(s): {', '.join(missing)}. Install ffmpeg "
            "(macOS: brew install ffmpeg; Debian/Ubuntu: apt install ffmpeg)."
        )


# --------------------------------------------------------------------------- #
# source classification
# --------------------------------------------------------------------------- #
DRIVE_ID_RE = re.compile(r"(?:/file/d/|[?&]id=|/d/)([A-Za-z0-9_-]{20,})")


def classify(source: str) -> tuple[str, str]:
    """Return (kind, normalized) where kind in {local, gdrive, url}."""
    p = Path(source).expanduser()
    if p.exists():
        if p.is_dir():
            die(f"{source!r} is a directory, not a media file")
        return "local", str(p.resolve())

    if re.match(r"^https?://", source, re.I):
        if "drive.google.com" in source or "docs.google.com" in source:
            return "gdrive", source
        return "url", source

    # not an existing path and not an http(s) URL
    if "://" in source or source.lower().startswith(("http", "www.")):
        die(f"{source!r} looks like a malformed URL (use a full http(s):// URL)")
    die(f"{source!r} is neither an existing file nor an http(s) URL")


# --------------------------------------------------------------------------- #
# acquisition
# --------------------------------------------------------------------------- #
def _run(cmd: list[str], *, capture: bool = False) -> subprocess.CompletedProcess:
    """Run a subprocess; keep our stdout pristine.

    Engine/yt-dlp stdout is redirected to our stderr (or captured); never to our
    stdout. On capture=True both streams are captured for diagnostics.
    """
    if capture:
        return subprocess.run(cmd, capture_output=True, text=True)
    return subprocess.run(cmd, stdout=sys.stderr)


def download_url(url: str, tmp: Path) -> Path:
    """Download best audio via yt-dlp (Python API). Returns local media path."""
    import yt_dlp

    outtmpl = str(tmp / "%(title).80s.%(ext)s")
    opts = {
        "format": "bestaudio/best",
        "outtmpl": outtmpl,
        "restrictfilenames": True,
        "noplaylist": True,
        "quiet": _QUIET or not _VERBOSE,
        "no_warnings": _QUIET,
        "noprogress": not is_interactive(),
        "logtostderr": True,
    }
    log(f"downloading: {url}")
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
            path = Path(ydl.prepare_filename(info))
    except Exception as e:  # yt_dlp.utils.DownloadError and friends
        raise AcquisitionError(str(e).strip().splitlines()[-1] if str(e) else repr(e))

    if not path.exists():
        # yt-dlp may have remuxed/renamed; grab whatever landed in tmp
        files = [f for f in tmp.iterdir() if f.is_file()]
        if not files:
            raise AcquisitionError("yt-dlp reported success but no file was downloaded")
        path = max(files, key=lambda f: f.stat().st_size)
    return path


GDRIVE_HOST = "https://drive.usercontent.google.com/download"


def _curl(url: str, dest: Path, jar: Path) -> subprocess.CompletedProcess:
    # -S surfaces errors under -s; connect-timeout + speed-limit/-time abort a
    # stalled transfer (< 1KB/s for 60s) without capping a slow large download.
    return _run(
        [
            "curl", "-sSL", "--connect-timeout", "30",
            "--speed-limit", "1024", "--speed-time", "60",
            "-c", str(jar), "-b", str(jar), "-o", str(dest), url,
        ],
        capture=True,
    )


def _is_html(path: Path) -> bool:
    # read only the first bytes; the download may be many GB
    with path.open("rb") as f:
        head = f.read(1024).lstrip().lower()
    return head.startswith((b"<!doctype html", b"<html")) or b"<html" in head


def _form_value(html: str, name: str) -> Optional[str]:
    """Pull a hidden form field value, tolerant of attribute order and quotes."""
    q = r'["\']'
    pats = (
        rf'name={q}{re.escape(name)}{q}[^>]*?value={q}([^"\']*){q}',
        rf'value={q}([^"\']*){q}[^>]*?name={q}{re.escape(name)}{q}',
    )
    for pat in pats:
        m = re.search(pat, html, re.I)
        if m:
            return m.group(1)
    return None


def download_gdrive(url: str, tmp: Path, *, direct: bool = False) -> Path:
    """Download a Google Drive file.

    yt-dlp first (handles most shared files), then a direct download from
    drive.usercontent.google.com with a static confirm token, which still serves
    large files behind the virus-scan interstitial. direct=True skips yt-dlp.
    """
    if not direct:
        try:
            return download_url(url, tmp)
        except AcquisitionError as e:
            log(f"yt-dlp could not fetch the Drive file ({e}); trying direct download")

    m = DRIVE_ID_RE.search(url)
    if not m:
        die(
            "could not extract a Google Drive file id from the URL. "
            "Use a /file/d/<ID>/view or ?id=<ID> link to a shared file."
        )
    file_id = m.group(1)
    if shutil.which("curl") is None:
        die("curl not found; needed for the Google Drive direct download")

    jar = tmp / "gdrive_cookies.txt"
    dest = tmp / f"gdrive_{file_id}"
    base = f"{GDRIVE_HOST}?id={file_id}&export=download"
    log("downloading from Google Drive")
    cp = _curl(f"{base}&confirm=t", dest, jar)
    if cp.returncode != 0 or not dest.exists() or dest.stat().st_size == 0:
        err = (cp.stderr or "").strip()
        die(
            "Google Drive download failed. The file may be private, not shared "
            "('anyone with the link'), or the id may be wrong."
            + (f" curl: {err}" if err else "")
        )

    # If confirm=t did not clear the virus-scan interstitial, parse the real
    # confirm token (and uuid) out of the returned form and retry once.
    if _is_html(dest):
        html = dest.read_text(errors="replace")
        confirm = _form_value(html, "confirm")
        uuid = _form_value(html, "uuid")
        if confirm:
            retry = f"{base}&confirm={confirm}" + (f"&uuid={uuid}" if uuid else "")
            log("clearing Drive virus-scan interstitial")
            cp = _curl(retry, dest, jar)
        if cp.returncode != 0 or not dest.exists() or dest.stat().st_size == 0 or _is_html(dest):
            die(
                "Google Drive returned a web page, not a media file. The link is "
                "private, view-only (download disabled), or rate-limited (too many "
                "recent downloads). Confirm it is shared with 'anyone with the link' "
                "and retry later."
            )
    return dest


def acquire(kind: str, source: str, tmp: Path, *, drive_direct: bool = False) -> tuple[Path, str]:
    """Return (media_path, slug). Local inputs are never copied or modified."""
    if kind == "local":
        p = Path(source)
        # the user's own filename is already valid on disk, so keep it as-is
        return p, p.stem
    try:
        if kind == "gdrive":
            media = download_gdrive(source, tmp, direct=drive_direct)
        else:
            media = download_url(source, tmp)
    except AcquisitionError as e:
        die(f"download failed: {e}")
    return media, _slugify(media.stem)


def _slugify(stem: str) -> str:
    """Sanitize a URL-derived title into a safe, readable output stem."""
    # drop a trailing container extension the title may carry (e.g. "clip.mp4")
    base, _, ext = stem.rpartition(".")
    if base and ext.lower() in MEDIA_EXTS:
        stem = base
    slug = re.sub(r"\s+", "_", stem.strip())
    slug = re.sub(r"[^A-Za-z0-9._-]", "", slug)
    slug = slug.strip("._-")
    return slug or "transcript"


# --------------------------------------------------------------------------- #
# validation + conversion
# --------------------------------------------------------------------------- #
def has_audio_stream(path: Path) -> bool:
    cp = _run(
        [
            "ffprobe", "-v", "error", "-select_streams", "a",
            "-show_entries", "stream=codec_type", "-of", "csv=p=0", str(path),
        ],
        capture=True,
    )
    return cp.returncode == 0 and "audio" in (cp.stdout or "")


def is_probeable_media(path: Path) -> bool:
    cp = _run(["ffprobe", "-v", "error", "-show_format", str(path)], capture=True)
    return cp.returncode == 0


def to_wav(media: Path, tmp: Path, slug: str) -> Path:
    """Validate the media, then convert it to 16k mono wav."""
    if not is_probeable_media(media):
        die(
            f"{media.name!r} is not a valid media file (ffprobe could not read it). "
            "If this came from a URL, the server likely returned an error or "
            "permission page instead of media."
        )
    if not has_audio_stream(media):
        die(
            f"{media.name!r} has no audio track to transcribe "
            "(e.g. a silent screen recording)."
        )
    wav = tmp / f"{slug}.wav"
    log("converting to 16kHz mono wav")
    cmd = ["ffmpeg", "-nostdin", "-y", "-i", str(media), "-vn", "-ar", "16000", "-ac", "1", str(wav)]
    if not _VERBOSE:
        cmd[1:1] = ["-loglevel", "error"]
    cp = _run(cmd, capture=not _VERBOSE)
    if cp.returncode != 0 or not wav.exists() or wav.stat().st_size == 0:
        detail = (cp.stderr or "").strip() if hasattr(cp, "stderr") and cp.stderr else ""
        die(f"ffmpeg failed to extract audio{': ' + detail if detail else ''}")
    return wav


# --------------------------------------------------------------------------- #
# transcription
# --------------------------------------------------------------------------- #
def resolve_engine(model: str) -> tuple[str, str]:
    """Map --model to (engine, hf_model_id). engine in {parakeet, whisper}."""
    if model == "parakeet":
        return "parakeet", PARAKEET_MODEL
    if model == "whisper":
        return "whisper", WHISPER_MODEL
    # custom HF id: infer engine from the name
    if "whisper" in model.lower():
        return "whisper", model
    return "parakeet", model


def transcribe(wav: Path, engine: str, hf_model: str, fmt: str, language: Optional[str], outdir: Path) -> None:
    # both MLX engines run via uvx (lazy, not in the script's deps)
    if shutil.which("uvx") is None:
        die("uvx not found; needed to run the MLX engines. Install uv: https://docs.astral.sh/uv/")
    if engine == "parakeet":
        if language:
            warn("parakeet auto-detects language; --language is ignored. Use --model whisper to force a language.")
        cmd = [
            "uvx", "--from", "parakeet-mlx>=0.3", "parakeet-mlx", str(wav),
            "--model", hf_model,
            "--output-dir", str(outdir),
            "--output-format", fmt,
        ]
    else:  # whisper
        cmd = [
            "uvx", "--from", "mlx-whisper>=0.4", "mlx_whisper", str(wav),
            "--model", hf_model,
            "--output-dir", str(outdir),
            "--output-format", fmt,
        ]
        if language:
            cmd += ["--language", language]
        if fmt == "json":
            cmd += ["--word-timestamps", "True"]

    log(f"transcribing with {engine} ({hf_model})")
    cp = _run(cmd, capture=_QUIET)
    if cp.returncode != 0:
        detail = (cp.stderr or cp.stdout or "").strip() if _QUIET else ""
        die(f"{engine} transcription failed{': ' + detail[-500:] if detail else ' (see logs above)'}")


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
@app.command()
def main(
    source: str = typer.Argument(..., help="A URL (Loom, YouTube, Google Drive, ...) or a local audio/video file."),
    model: str = typer.Option("parakeet", "--model", "-m", help="parakeet (default), whisper, or a HuggingFace model id."),
    fmt: str = typer.Option("txt", "--format", "-f", help="Output format: txt, srt, vtt, json."),
    output_dir: Path = typer.Option(Path.cwd(), "--output-dir", "-o", help="Directory for the transcript (default: cwd)."),
    language: Optional[str] = typer.Option(None, "--language", "-l", help="Language code (whisper only; parakeet auto-detects)."),
    keep_media: bool = typer.Option(False, "--keep-media", help="Keep the downloaded audio file in the output dir (audio only, not video)."),
    drive_direct: bool = typer.Option(False, "--drive-direct", help="For a Google Drive URL, skip yt-dlp and download directly (use if yt-dlp fails)."),
    force: bool = typer.Option(False, "--force", help="Overwrite an existing transcript."),
    quiet: bool = typer.Option(False, "--quiet", "-q", help="Suppress progress logs (errors still shown)."),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show full download/transcribe output."),
):
    """Transcribe audio/video from a URL or local file to a text transcript.

    Examples:

      transcribe.py https://www.loom.com/share/<id>

      transcribe.py talk.mp4 --format srt -o ~/transcripts

      transcribe.py interview.mp3 --model whisper --language de

      transcribe.py "https://drive.google.com/file/d/<id>/view" --keep-media
    """
    global _QUIET, _VERBOSE
    _QUIET, _VERBOSE = quiet, verbose
    if quiet and verbose:
        die("--quiet and --verbose are mutually exclusive")

    fmt = fmt.lower()
    if fmt not in FORMATS:
        die(f"unknown format {fmt!r}; choose one of: {', '.join(FORMATS)}")

    check_platform()
    check_prereqs()
    output_dir = output_dir.expanduser().resolve()
    try:
        output_dir.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        die(f"cannot create output directory {output_dir}: {e}")

    engine, hf_model = resolve_engine(model)
    kind, normalized = classify(source)
    if drive_direct and kind != "gdrive":
        warn("--drive-direct only applies to Google Drive URLs; ignoring it.")

    tmp = Path(tempfile.mkdtemp(prefix="transcribe-"))
    try:
        media, slug = acquire(kind, normalized, tmp, drive_direct=drive_direct)

        final = output_dir / f"{slug}.{fmt}"
        # never clobber the user's own input file, even with --force
        if kind == "local" and final.resolve() == Path(media).resolve():
            die(
                f"refusing to write the transcript over the input file ({final}). "
                "Pick a different --output-dir or --format."
            )
        if final.is_dir():
            die(f"output path is a directory, not a file: {final}. Pick a different --output-dir or slug.")
        if (final.exists() or final.is_symlink()) and not force:
            die(f"output already exists: {final}\nUse --force to overwrite.")

        wav = to_wav(media, tmp, slug)
        engine_out = tmp / "out"
        engine_out.mkdir(exist_ok=True)
        transcribe(wav, engine, hf_model, fmt, language, engine_out)

        produced = sorted(engine_out.glob(f"*.{fmt}"))
        if not produced:
            die(f"{engine} produced no .{fmt} output (transcription may have yielded nothing)")
        # prefer the one matching our slug
        src_file = next((f for f in produced if f.stem == slug), produced[0])
        # re-check just before the move to close the create-during-transcription window
        if not force and (final.exists() or final.is_symlink()):
            die(f"output appeared during transcription: {final}\nUse --force to overwrite.")
        shutil.move(str(src_file), str(final))
        if final.stat().st_size == 0:
            warn("transcript is empty; no speech was detected in the audio.")

        if keep_media and kind != "local":
            kept = output_dir / media.name
            if not kept.exists() or force:
                shutil.move(str(media), str(kept))
                log(f"kept media: {kept}")

        log(f"transcript written ({_human_size(final)})")
        print(final)  # the only thing on stdout
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _human_size(p: Path) -> str:
    n = float(p.stat().st_size)
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f}{unit}" if unit == "B" else f"{n:.1f}{unit}"
        n /= 1024
    return f"{n:.1f}GB"


if __name__ == "__main__":
    app()
