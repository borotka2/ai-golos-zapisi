"""Демо-менеджер + примеры записей для показа UI (без реального ИИ)."""
from datetime import datetime, timedelta
from pathlib import Path

from app.auth import hash_password
from app.database import SessionLocal, UPLOADS_DIR, Base, engine
from app.main import migrate_db
from app.models import FileType, Recording, RecordingStatus, User, UserRole

Base.metadata.create_all(bind=engine)
migrate_db()

db = SessionLocal()
try:
    mgr = db.query(User).filter(User.username == "manager").first()
    if not mgr:
        mgr = User(
            username="manager",
            password_hash=hash_password("manager123"),
            full_name="Демо Менеджер",
            role=UserRole.manager,
            is_approved=True,
        )
        db.add(mgr)
        db.commit()
        db.refresh(mgr)
        print("Создан manager / manager123")
    else:
        mgr.is_approved = True
        db.commit()
        print("Менеджер уже есть: manager / manager123")

    # Уже есть демо-строки?
    existing = db.query(Recording).filter(Recording.user_id == mgr.id).count()
    if existing >= 3:
        print(f"Уже {existing} записей — не дублируем")
    else:
        demo_dir = UPLOADS_DIR / str(mgr.id) / "demo"
        demo_dir.mkdir(parents=True, exist_ok=True)
        samples = [
            ("2026-07-18_10-15-22_380501112233.wav", datetime(2026, 7, 18, 10, 15, 22), "380501112233"),
            ("2026-07-19_14-42-03_380679998877.wav", datetime(2026, 7, 19, 14, 42, 3), "380679998877"),
            ("2026-07-20_09-05-41_380441234567.wav", datetime(2026, 7, 20, 9, 5, 41), "380441234567"),
        ]
        for name, when, phone in samples:
            path = demo_dir / name
            if not path.exists():
                path.write_bytes(b"RIFF....WAVEdemo")  # заглушка, не для реального анализа
            rec = Recording(
                user_id=mgr.id,
                filename=name,
                stored_path=str(path),
                file_type=FileType.audio,
                status=RecordingStatus.pending,
                source="microsip",
                recorded_at=when,
                phone=phone,
                uploaded_at=when + timedelta(minutes=1),
            )
            db.add(rec)
        db.commit()
        print("Добавлены 3 демо-записи MicroSIP (ждут «Анализ ИИ»)")

    print("OK — логин: manager / manager123")
finally:
    db.close()
