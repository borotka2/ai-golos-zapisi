"""Парсинг имён файлов MicroSIP и хелперы для автозагрузки записей."""
from __future__ import annotations

import hashlib
import re
from datetime import datetime
from pathlib import Path

# Типичные шаблоны MicroSIP / softphone:
# 2023-03-14_15-42-30_380501234567.wav
# 20230314-154230-380501234567.mp3
# call_2023-03-14_154230.wav
# 14.03.2023 15-42-30.wav
_DATE_PATTERNS = [
    # YYYY-MM-DD_HH-MM-SS or YYYY-MM-DD_HHMMSS or YYYY-MM-DD-HH-MM-SS
    re.compile(
        r"(?P<y>\d{4})[-_.](?P<m>\d{2})[-_.](?P<d>\d{2})[T_\s-]*(?P<H>\d{2})[:\-.]?(?P<M>\d{2})[:\-.]?(?P<S>\d{2})?"
    ),
    # YYYYMMDD_HHMMSS or YYYYMMDD-HHMMSS
    re.compile(
        r"(?P<y>\d{4})(?P<m>\d{2})(?P<d>\d{2})[_-](?P<H>\d{2})(?P<M>\d{2})(?P<S>\d{2})?"
    ),
    # DD.MM.YYYY HH-MM-SS / DD-MM-YYYY
    re.compile(
        r"(?P<d>\d{2})[.\-](?P<m>\d{2})[.\-](?P<y>\d{4})[_\s-]*(?P<H>\d{2})[:\-.]?(?P<M>\d{2})[:\-.]?(?P<S>\d{2})?"
    ),
]

# Номер телефона: 7–15 цифр, часто в конце имени
_PHONE_RE = re.compile(r"(?<!\d)(\+?\d{7,15})(?!\d)")

AUDIO_EXTS = {".mp3", ".wav", ".m4a", ".ogg", ".flac", ".aac", ".wma"}


def is_audio_file(path: Path | str) -> bool:
    return Path(path).suffix.lower() in AUDIO_EXTS


def parse_recorded_at(filename: str, fallback_mtime: float | None = None) -> datetime | None:
    """Достаёт дату/время звонка из имени файла MicroSIP, иначе из mtime."""
    name = Path(filename).stem
    for pattern in _DATE_PATTERNS:
        m = pattern.search(name)
        if not m:
            continue
        g = m.groupdict()
        try:
            return datetime(
                int(g["y"]),
                int(g["m"]),
                int(g["d"]),
                int(g.get("H") or 0),
                int(g.get("M") or 0),
                int(g.get("S") or 0),
            )
        except (ValueError, TypeError):
            continue
    if fallback_mtime is not None:
        try:
            return datetime.fromtimestamp(fallback_mtime)
        except (OSError, ValueError, OverflowError):
            return None
    return None


def parse_phone(filename: str) -> str | None:
    name = Path(filename).stem
    # Берём последний «телефонный» фрагмент (часто номер абонента в конце)
    matches = _PHONE_RE.findall(name)
    if not matches:
        return None
    phone = matches[-1].lstrip("+")
    # Отсекаем куски, которые на самом деле дата YYYYMMDD / HHMMSS
    if len(phone) == 8 and phone.startswith("20"):
        return matches[-2].lstrip("+") if len(matches) > 1 else None
    return phone


def file_sha256(path: Path, chunk_size: int = 1024 * 1024) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def display_when(recorded_at: datetime | None, uploaded_at: datetime | None) -> str:
    dt = recorded_at or uploaded_at
    if not dt:
        return "—"
    return dt.strftime("%d.%m.%Y %H:%M")
