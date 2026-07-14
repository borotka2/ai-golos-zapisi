"""Re-transcribe and re-analyze all recordings with current AI rules."""
import threading
import time

from app.database import SessionLocal
from app.main import run_analysis
from app.models import Recording, RecordingStatus

MAX_PARALLEL = 2
_semaphore = threading.Semaphore(MAX_PARALLEL)


def _run_with_limit(recording_id: int) -> None:
    with _semaphore:
        print(f"[start] recording #{recording_id}", flush=True)
        run_analysis(recording_id)
        print(f"[done] recording #{recording_id}", flush=True)


def main() -> None:
    db = SessionLocal()
    try:
        ids = [r.id for r in db.query(Recording).order_by(Recording.id).all()]
        for recording_id in ids:
            rec = db.query(Recording).filter(Recording.id == recording_id).first()
            if rec:
                rec.status = RecordingStatus.pending
                rec.error_message = None
        db.commit()
        print(f"[info] queued all {len(ids)} recordings: {ids}", flush=True)
    finally:
        db.close()

    threads: list[threading.Thread] = []
    for recording_id in ids:
        thread = threading.Thread(target=_run_with_limit, args=(recording_id,), daemon=True)
        thread.start()
        threads.append(thread)
        time.sleep(0.5)

    for thread in threads:
        thread.join()

    db = SessionLocal()
    try:
        by_status: dict[str, int] = {}
        for recording in db.query(Recording).all():
            by_status[recording.status.value] = by_status.get(recording.status.value, 0) + 1
        print("[summary]", by_status, flush=True)
    finally:
        db.close()


if __name__ == "__main__":
    main()