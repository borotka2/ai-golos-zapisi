import subprocess
from pathlib import Path

import imageio_ffmpeg


def get_audio_duration_seconds(path: Path) -> float | None:
    if not path.exists():
        return None
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    try:
        proc = subprocess.run(
            [
                ffmpeg,
                "-hide_banner",
                "-i",
                str(path),
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
            check=False,
        )
        for line in (proc.stderr or "").splitlines():
            if "Duration:" in line:
                raw = line.split("Duration:", 1)[1].split(",", 1)[0].strip()
                hours, minutes, seconds = raw.split(":")
                return int(hours) * 3600 + int(minutes) * 60 + float(seconds)
    except Exception:
        return None
    return None


def format_duration(seconds: float | None) -> str:
    if seconds is None or seconds <= 0:
        return "—"
    total = int(round(seconds))
    minutes, secs = divmod(total, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"