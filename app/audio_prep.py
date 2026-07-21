import subprocess
import tempfile
from pathlib import Path

MAX_UPLOAD_MB = 20
CHUNK_SECONDS = 480


def _ffmpeg_exe() -> str | None:
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return None


def _run_ffmpeg(args: list[str], timeout: int = 900) -> None:
    exe = _ffmpeg_exe()
    if not exe:
        raise RuntimeError(
            "На сервере нет ffmpeg (imageio-ffmpeg). "
            "Загрузите mp3 до ~20 МБ или установите imageio-ffmpeg в vendor."
        )
    result = subprocess.run(
        [exe, *args],
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    if result.returncode != 0:
        err = (result.stderr or result.stdout or "ffmpeg error")[-500:]
        raise RuntimeError(f"Ошибка обработки аудио: {err}")


def _compress(path: Path, out: Path) -> Path:
    _run_ffmpeg(
        [
            "-y",
            "-i",
            str(path),
            "-ac",
            "1",
            "-ar",
            "16000",
            "-b:a",
            "32k",
            str(out),
        ]
    )
    return out


def _split(path: Path, out_dir: Path) -> list[Path]:
    pattern = str(out_dir / "part_%03d.mp3")
    _run_ffmpeg(
        [
            "-y",
            "-i",
            str(path),
            "-f",
            "segment",
            "-segment_time",
            str(CHUNK_SECONDS),
            "-ac",
            "1",
            "-ar",
            "16000",
            "-b:a",
            "32k",
            "-reset_timestamps",
            "1",
            pattern,
        ]
    )
    parts = sorted(out_dir.glob("part_*.mp3"))
    if not parts:
        raise RuntimeError("Не удалось разделить аудиофайл на части")
    return parts


def prepare_audio_chunks(path: Path) -> list[Path]:
    """Готовит аудио к Whisper. Без ffmpeg — отдаём исходник, если он достаточно маленький."""
    size_mb = path.stat().st_size / (1024 * 1024)
    work_dir = Path(tempfile.mkdtemp(prefix="ai-golos-audio-"))
    has_ffmpeg = _ffmpeg_exe() is not None

    # Маленький mp3 — без перекодирования
    if path.suffix.lower() == ".mp3" and size_mb <= 20:
        return [path]

    if not has_ffmpeg:
        if size_mb <= MAX_UPLOAD_MB:
            return [path]
        raise RuntimeError(
            f"Файл слишком большой ({size_mb:.0f} МБ), а ffmpeg на сервере не установлен. "
            "Загрузите запись короче или mp3 до 20 МБ."
        )

    if size_mb <= MAX_UPLOAD_MB:
        single = work_dir / "single.mp3"
        if path.suffix.lower() == ".mp3" and size_mb <= 10:
            return [path]
        return [_compress(path, single)]

    parts = _split(path, work_dir)
    ready: list[Path] = []
    for part in parts:
        part_mb = part.stat().st_size / (1024 * 1024)
        if part_mb <= MAX_UPLOAD_MB:
            ready.append(part)
            continue
        smaller = work_dir / f"{part.stem}_small.mp3"
        _compress(part, smaller)
        if smaller.stat().st_size / (1024 * 1024) > MAX_UPLOAD_MB:
            raise RuntimeError(
                f"Часть аудио всё ещё слишком большая ({part_mb:.0f} МБ). "
                "Загрузите более короткую запись (до 30–40 минут)."
            )
        ready.append(smaller)
    return ready
