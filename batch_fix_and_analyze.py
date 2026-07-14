"""Fix old file paths and queue AI analysis for recordings that need it."""
import threading
import time
from pathlib import Path

from app.database import SessionLocal
from app.main import run_analysis
from app.models import Recording, RecordingStatus

OLD_ROOT = Path(r"C:\Users\Edik\Desktop\ai-golos-zapisi")
NEW_ROOT = Path(__file__).resolve().parent
MIN_TRANSCRIPT = 100
MAX_PARALLEL = 2

_semaphore = threading.Semaphore(MAX_PARALLEL)


def _run_with_limit(recording_id: int) -> None:
    with _semaphore:
        print(f"[start] recording #{recording_id}", flush=True)
        run_analysis(recording_id)
        print(f"[done] recording #{recording_id}", flush=True)


def needs_analysis(recording: Recording) -> bool:
    if recording.status in (RecordingStatus.pending, RecordingStatus.error, RecordingStatus.processing):
        return True
    transcript = (recording.transcript or "").strip()
    return len(transcript) < MIN_TRANSCRIPT


def main() -> None:
    db = SessionLocal()
    try:
        recordings = db.query(Recording).order_by(Recording.id).all()
        fixed_paths = 0
        to_analyze: list[int] = []

        for recording in recordings:
            stored = Path(recording.stored_path)
            if not stored.exists():
                candidate = Path(str(recording.stored_path).replace(str(OLD_ROOT), str(NEW_ROOT)))
                if candidate.exists():
                    recording.stored_path = str(candidate)
                    fixed_paths += 1
                else:
                    print(f"[skip] file missing for #{recording.id}: {recording.filename}", flush=True)
                    continue

            if needs_analysis(recording):
                recording.status = RecordingStatus.pending
                recording.error_message = None
                to_analyze.append(recording.id)

        db.commit()
        print(f"[info] fixed paths: {fixed_paths}", flush=True)
        print(f"[info] queued for analysis: {len(to_analyze)} -> {to_analyze}", flush=True)
    finally:
        db.close()

    threads: list[threading.Thread] = []
    for recording_id in to_analyze:
        thread = threading.Thread(target=_run_with_limit, args=(recording_id,), daemon=True)
        thread.start()
        threads.append(thread)
        time.sleep(0.5)

    for thread in threads:
        thread.join()

    db = SessionLocal()
    try:
        by_status = {}
        for recording in db.query(Recording).all():
            by_status[recording.status.value] = by_status.get(recording.status.value, 0) + 1
        print("[summary]", by_status, flush=True)
    finally:
        db.close()


if __name__ == "__main__":
    main()