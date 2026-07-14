import json
import shutil
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from jinja2 import Environment, FileSystemLoader, select_autoescape
from sqlalchemy import func, text
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool
from starlette.middleware.sessions import SessionMiddleware

from .ai_analyzer import ask_about_recording, detect_file_type, openai_config_status, process_recording_file
from .env_config import auto_import_keys, get_env_values, mask_key, save_env_values
from .auth import (
    SECRET_KEY,
    can_access_recording,
    find_user,
    get_current_user,
    hash_password,
    require_admin,
)
from .database import UPLOADS_DIR, Base, engine, get_db
from .recording_files import format_duration, get_audio_duration_seconds
from .models import Analysis, FileType, Recording, RecordingStatus, User, UserRole

load_dotenv()

# Параллельный анализ: несколько записей одновременно (очередь + воркеры)
ANALYSIS_WORKERS = 7
_analysis_executor = ThreadPoolExecutor(max_workers=ANALYSIS_WORKERS, thread_name_prefix="ai-analyze")
_analysis_queue: list[int] = []
_analysis_queue_lock = threading.Lock()
_analysis_dispatcher_started = False
_analysis_active = 0
_analysis_active_lock = threading.Lock()
# Пауза между стартами, чтобы API (Groq/DeepSeek) не отдавал rate-limit на пачке
ANALYSIS_START_GAP_SEC = 1.2

app = FastAPI(title="Панель анализа разговоров")
app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY)
app.mount("/static", StaticFiles(directory=Path(__file__).parent.parent / "static"), name="static")
_template_dir = Path(__file__).parent.parent / "templates"
_jinja_env = Environment(
    loader=FileSystemLoader(_template_dir),
    autoescape=select_autoescape(),
    cache_size=0,
)
def template_context(request: Request) -> dict:
    user_id = request.session.get("user_id")
    if not user_id:
        return {}
    from .database import SessionLocal

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.id == user_id).first()
        if user and user.role == UserRole.admin:
            count = (
                db.query(func.count(User.id))
                .filter(User.role == UserRole.manager, User.is_approved.is_(False))
                .scalar()
            )
            return {"pending_count": count or 0}
    finally:
        db.close()
    return {}


templates = Jinja2Templates(env=_jinja_env, context_processors=[template_context])


def migrate_db():
    with engine.begin() as conn:
        cols = {row[1] for row in conn.execute(text("PRAGMA table_info(users)")).fetchall()}
        if "is_approved" not in cols:
            conn.execute(text("ALTER TABLE users ADD COLUMN is_approved INTEGER NOT NULL DEFAULT 1"))
        conn.execute(text("UPDATE users SET is_approved = 1 WHERE role = 'admin' OR is_approved IS NULL"))


def init_db():
    Base.metadata.create_all(bind=engine)
    migrate_db()
    from .database import SessionLocal

    db = SessionLocal()
    try:
        if not db.query(User).filter(User.username == "admin").first():
            admin = User(
                username="admin",
                password_hash=hash_password("admin123"),
                full_name="Администратор",
                role=UserRole.admin,
                is_approved=True,
            )
            db.add(admin)
            try:
                db.commit()
            except Exception:
                db.rollback()
    finally:
        db.close()


def recover_stuck_analyses():
    """После перезапуска сервера потоки анализа умирают — перезапускаем зависшие записи."""
    from .database import SessionLocal

    db = SessionLocal()
    try:
        stuck = (
            db.query(Recording)
            .filter(Recording.status.in_((RecordingStatus.processing, RecordingStatus.pending)))
            .all()
        )
        for recording in stuck:
            recording.status = RecordingStatus.pending
            recording.error_message = None
            db.commit()
            schedule_analysis(recording.id)
        if stuck:
            print(f"[startup] Перезапущен анализ для {len(stuck)} записей")
    finally:
        db.close()


@app.on_event("startup")
def on_startup():
    init_db()
    auto_import_keys()
    load_dotenv(override=True)
    recover_stuck_analyses()
    ok, message = openai_config_status()
    print(f"[startup] Параллельный анализ: до {ANALYSIS_WORKERS} записей одновременно")
    if ok:
        print(f"[startup] {message}")
    else:
        print(f"[startup] ВНИМАНИЕ: {message}")
        print("[startup] Файл: .env в папке проекта | Ключ: https://platform.openai.com/api-keys")


def _friendly_analysis_error(exc: Exception) -> str:
    text = str(exc).strip()
    lower = text.lower()
    if "connection error" in lower or "certificate_verify_failed" in lower:
        return "Ошибка соединения с сервисом ИИ. Повторите анализ через кнопку ниже."
    if "rate limit" in lower or "429" in lower or "too many requests" in lower:
        return "Слишком много запросов к ИИ. Подождите 1–2 минуты и нажмите «Повторить анализ»."
    if "файл пустой" in lower or "не удалось получить текст" in lower:
        return "Не удалось распознать речь в записи. Проверьте, что файл не пустой и формат поддерживается."
    if "database is locked" in lower or ("sqlite" in lower and "locked" in lower):
        return "База занята (много файлов сразу). Повторите анализ — очередь уже настроена."
    if not text or text in ("1", "0", "None", "Error"):
        return "Ошибка анализа. Нажмите «Повторить анализ» — файл уже сохранён."
    return text[:500]


def _ensure_dispatcher() -> None:
    global _analysis_dispatcher_started
    if _analysis_dispatcher_started:
        return
    with _analysis_queue_lock:
        if _analysis_dispatcher_started:
            return
        _analysis_dispatcher_started = True
        t = threading.Thread(target=_analysis_dispatcher_loop, name="ai-analyze-dispatcher", daemon=True)
        t.start()


def schedule_analysis(recording_id: int) -> None:
    """Ставит запись в очередь — несколько файлов идут параллельно, без «ошибки 1» от rate-limit."""
    _ensure_dispatcher()
    with _analysis_queue_lock:
        if recording_id not in _analysis_queue:
            _analysis_queue.append(recording_id)


def _analysis_dispatcher_loop() -> None:
    global _analysis_active
    while True:
        recording_id = None
        with _analysis_active_lock:
            active = _analysis_active
        if active < ANALYSIS_WORKERS:
            with _analysis_queue_lock:
                if _analysis_queue:
                    recording_id = _analysis_queue.pop(0)
        if recording_id is None:
            time.sleep(0.35)
            continue
        with _analysis_active_lock:
            _analysis_active += 1
        _analysis_executor.submit(_run_analysis_wrapper, recording_id)
        time.sleep(ANALYSIS_START_GAP_SEC)


def _run_analysis_wrapper(recording_id: int) -> None:
    global _analysis_active
    try:
        run_analysis(recording_id)
    finally:
        with _analysis_active_lock:
            _analysis_active = max(0, _analysis_active - 1)


def run_analysis(recording_id: int):
    from .database import SessionLocal

    db = SessionLocal()
    try:
        recording = db.query(Recording).filter(Recording.id == recording_id).first()
        if not recording:
            return

        if recording.status == RecordingStatus.done and recording.analysis:
            return

        recording.status = RecordingStatus.processing
        recording.error_message = None
        db.commit()

        try:
            stored = Path(recording.stored_path)
            if not stored.exists() or stored.stat().st_size == 0:
                raise RuntimeError("Файл записи не найден или пустой")

            transcript, result = process_recording_file(
                stored,
                recording.file_type.value,
            )
            recording.transcript = transcript

            analysis = db.query(Analysis).filter(Analysis.recording_id == recording.id).first()
            if not analysis:
                analysis = Analysis(recording_id=recording.id)
                db.add(analysis)

            errors_list = result.get("errors") or []
            if not isinstance(errors_list, list):
                errors_list = []
            # Нормализуем ошибки: всегда объекты с полями (не «ошибка 1» / строка)
            normalized_errors = []
            for item in errors_list:
                if isinstance(item, dict):
                    normalized_errors.append({
                        "title": item.get("title") or item.get("name") or "Ошибка",
                        "quote": item.get("quote") or "",
                        "explanation": item.get("explanation") or item.get("description") or "",
                        "reason": item.get("reason") or "",
                        "better_response": item.get("better_response") or item.get("fix") or "",
                        "example_phrase": item.get("example_phrase") or item.get("example") or "",
                    })
                elif item:
                    normalized_errors.append({
                        "title": str(item)[:200],
                        "quote": "",
                        "explanation": str(item),
                        "reason": "",
                        "better_response": "",
                        "example_phrase": "",
                    })

            analysis.errors_json = json.dumps(
                {
                    "sections": result.get("sections") or {},
                    "errors": normalized_errors,
                    "missed_opportunities": result.get("missed_opportunities") or [],
                    "script_violations": result.get("script_violations") or [],
                    "weak_communication": result.get("weak_communication") or [],
                },
                ensure_ascii=False,
            )
            analysis.recommendations_json = json.dumps(
                result.get("recommendations") or [],
                ensure_ascii=False,
            )
            scores = result.get("scores") or {}
            if not isinstance(scores, dict):
                scores = {}
            analysis.scores_json = json.dumps(scores, ensure_ascii=False)
            try:
                analysis.total_score = float(result.get("total_score") or 0)
            except (TypeError, ValueError):
                analysis.total_score = 0.0
            analysis.summary = result.get("summary") or "Анализ выполнен"
            recording.status = RecordingStatus.done
            recording.error_message = None
        except Exception as exc:
            recording.status = RecordingStatus.error
            recording.error_message = _friendly_analysis_error(exc)
            print(f"[analyze] id={recording_id} ERROR: {exc}", flush=True)
        db.commit()
    except Exception as outer:
        print(f"[analyze] id={recording_id} fatal: {outer}", flush=True)
        try:
            db.rollback()
            recording = db.query(Recording).filter(Recording.id == recording_id).first()
            if recording:
                recording.status = RecordingStatus.error
                recording.error_message = _friendly_analysis_error(outer)
                db.commit()
        except Exception:
            pass
    finally:
        db.close()


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    if request.session.get("user_id"):
        return RedirectResponse("/dashboard", status_code=302)
    return RedirectResponse("/login", status_code=302)


@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    return templates.TemplateResponse(request, "login.html", {"error": None})


@app.post("/login", response_class=HTMLResponse)
def login_submit(request: Request, username: str = Form(...), password: str = Form(...), db: Session = Depends(get_db)):
    user, error_key = find_user(db, username.strip(), password)
    if error_key == "pending_approval":
        return templates.TemplateResponse(
            request,
            "login.html",
            {
                "error": None,
                "pending": True,
                "pending_name": user.full_name if user else username,
            },
            status_code=400,
        )
    if not user:
        return templates.TemplateResponse(
            request,
            "login.html",
            {"error": "Неверный логин или пароль", "pending": False},
            status_code=400,
        )
    request.session["user_id"] = user.id
    return RedirectResponse("/dashboard", status_code=302)


@app.get("/register", response_class=HTMLResponse)
def register_page(request: Request):
    if request.session.get("user_id"):
        return RedirectResponse("/dashboard", status_code=302)
    return templates.TemplateResponse(request, "register.html", {"error": None, "success": False})


@app.post("/register", response_class=HTMLResponse)
def register_submit(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    full_name: str = Form(...),
    db: Session = Depends(get_db),
):
    username = username.strip().lower()
    full_name = full_name.strip()

    if len(username) < 3:
        return templates.TemplateResponse(
            request,
            "register.html",
            {"error": "Логин — минимум 3 символа", "success": False},
            status_code=400,
        )
    if username == "admin":
        return templates.TemplateResponse(
            request,
            "register.html",
            {"error": "Этот логин зарезервирован", "success": False},
            status_code=400,
        )
    if len(password) < 6:
        return templates.TemplateResponse(
            request,
            "register.html",
            {"error": "Пароль — минимум 6 символов", "success": False},
            status_code=400,
        )
    if len(full_name) < 2:
        return templates.TemplateResponse(
            request,
            "register.html",
            {"error": "Укажите ваше имя — минимум 2 символа", "success": False},
            status_code=400,
        )
    if db.query(User).filter(User.username == username).first():
        return templates.TemplateResponse(
            request,
            "register.html",
            {"error": "Пользователь с таким логином уже есть", "success": False},
            status_code=400,
        )

    manager = User(
        username=username,
        password_hash=hash_password(password),
        full_name=full_name,
        role=UserRole.manager,
        is_approved=False,
    )
    db.add(manager)
    db.commit()
    return templates.TemplateResponse(request, "register.html", {"error": None, "success": True, "full_name": full_name})


@app.get("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", status_code=302)


def manager_stats(db: Session, user_id: int) -> dict:
    recordings = db.query(Recording).filter(Recording.user_id == user_id).all()
    done = [r for r in recordings if r.status == RecordingStatus.done and r.analysis]
    scores = [r.analysis.total_score for r in done]
    return {
        "total": len(recordings),
        "done": len(done),
        "pending": len([r for r in recordings if r.status in (RecordingStatus.pending, RecordingStatus.processing)]),
        "errors": len([r for r in recordings if r.status == RecordingStatus.error]),
        "avg_score": round(sum(scores) / len(scores), 1) if scores else 0,
        "history": [
            {
                "date": r.uploaded_at.strftime("%d.%m.%Y"),
                "filename": r.filename,
                "score": r.analysis.total_score if r.analysis else None,
            }
            for r in sorted(recordings, key=lambda x: x.uploaded_at)
            if r.analysis
        ],
    }


@app.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if user.role == UserRole.admin:
        managers = (
            db.query(User)
            .filter(User.role == UserRole.manager, User.is_approved.is_(True))
            .order_by(User.full_name)
            .all()
        )
        pending_count = (
            db.query(func.count(User.id))
            .filter(User.role == UserRole.manager, User.is_approved.is_(False))
            .scalar()
        )
        recordings = (
            db.query(Recording)
            .join(User)
            .order_by(Recording.uploaded_at.desc())
            .all()
        )
        return templates.TemplateResponse(
            request,
            "admin_dashboard.html",
            {
                "user": user,
                "managers": managers,
                "recordings": recordings,
                "total_recordings": len(recordings),
                "done_count": len([r for r in recordings if r.status == RecordingStatus.done]),
                "pending_count": pending_count or 0,
            },
        )

    recordings = (
        db.query(Recording)
        .filter(Recording.user_id == user.id)
        .order_by(Recording.uploaded_at.desc())
        .all()
    )
    return templates.TemplateResponse(
        request,
        "manager_dashboard.html",
        {
            "user": user,
            "recordings": recordings,
            "stats": manager_stats(db, user.id),
        },
    )


@app.post("/upload")
async def upload_files(
    request: Request,
    files: list[UploadFile] = File(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not files:
        raise HTTPException(status_code=400, detail="Файлы не выбраны")

    user_dir = UPLOADS_DIR / str(user.id) / datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    user_dir.mkdir(parents=True, exist_ok=True)

    saved = 0
    skipped = 0
    queued_ids: list[int] = []

    # Сначала сохраняем все файлы, потом ставим в очередь анализа — много записей за раз
    for upload in files:
        if not upload.filename:
            skipped += 1
            continue
        file_type = detect_file_type(upload.filename, upload.content_type or "")
        if file_type == "unknown":
            skipped += 1
            continue

        safe_name = Path(upload.filename.replace("\\", "/")).name
        dest = user_dir / f"{uuid.uuid4().hex}_{safe_name}"
        try:
            with dest.open("wb") as f:
                shutil.copyfileobj(upload.file, f)
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"Не удалось сохранить {safe_name}: {exc}") from exc

        if dest.stat().st_size == 0:
            dest.unlink(missing_ok=True)
            skipped += 1
            continue

        recording = Recording(
            user_id=user.id,
            filename=safe_name,
            stored_path=str(dest),
            file_type=FileType.audio if file_type == "audio" else FileType.text,
            status=RecordingStatus.pending,
        )
        db.add(recording)
        db.flush()
        queued_ids.append(recording.id)
        saved += 1

    if saved:
        db.commit()
        for rid in queued_ids:
            schedule_analysis(rid)
    else:
        db.rollback()

    wants_json = "application/json" in (request.headers.get("accept") or "")

    if saved == 0:
        msg = (
            "Нет подходящих файлов. Нужны: mp3, wav, m4a, ogg, txt. "
            "Выберите папку целиком или отдельные файлы (не ярлыки и не zip)."
        )
        if wants_json:
            raise HTTPException(status_code=400, detail=msg)
        from urllib.parse import quote

        return RedirectResponse(f"/dashboard?upload_error={quote(msg)}", status_code=302)

    if wants_json:
        return JSONResponse({
            "ok": True,
            "saved": saved,
            "skipped": skipped,
            "queued": len(queued_ids),
            "redirect": "/dashboard",
        })

    return RedirectResponse("/dashboard", status_code=302)


@app.get("/recording/{recording_id}", response_class=HTMLResponse)
def recording_detail(
    recording_id: int,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    recording = db.query(Recording).filter(Recording.id == recording_id).first()
    if not recording or not can_access_recording(user, recording.user_id):
        raise HTTPException(status_code=404, detail="Запись не найдена")

    analysis_data = None
    if recording.analysis:
        try:
            errors_payload = json.loads(recording.analysis.errors_json or "{}")
        except json.JSONDecodeError:
            errors_payload = {}
        if not isinstance(errors_payload, dict):
            errors_payload = {}
        raw_errors = errors_payload.get("errors") or []
        if not isinstance(raw_errors, list):
            raw_errors = []
        safe_errors = []
        for item in raw_errors:
            if isinstance(item, dict):
                safe_errors.append({
                    "title": item.get("title") or "Ошибка",
                    "quote": item.get("quote") or "",
                    "explanation": item.get("explanation") or "",
                    "reason": item.get("reason") or "",
                    "better_response": item.get("better_response") or "",
                    "example_phrase": item.get("example_phrase") or "",
                })
            elif item:
                safe_errors.append({
                    "title": str(item)[:200],
                    "quote": "",
                    "explanation": str(item),
                    "reason": "",
                    "better_response": "",
                    "example_phrase": "",
                })
        try:
            recommendations = json.loads(recording.analysis.recommendations_json or "[]")
        except json.JSONDecodeError:
            recommendations = []
        if not isinstance(recommendations, list):
            recommendations = [str(recommendations)]
        try:
            scores = json.loads(recording.analysis.scores_json or "{}")
        except json.JSONDecodeError:
            scores = {}
        if not isinstance(scores, dict):
            scores = {}
        analysis_data = {
            "sections": errors_payload.get("sections") if isinstance(errors_payload.get("sections"), dict) else {},
            "errors": {
                "errors": safe_errors,
                "missed_opportunities": errors_payload.get("missed_opportunities") or [],
                "script_violations": errors_payload.get("script_violations") or [],
                "weak_communication": errors_payload.get("weak_communication") or [],
            },
            "recommendations": recommendations,
            "scores": scores,
            "total_score": recording.analysis.total_score or 0,
            "summary": recording.analysis.summary or "",
        }

    file_path = Path(recording.stored_path)
    duration = format_duration(get_audio_duration_seconds(file_path))

    return templates.TemplateResponse(
        request,
        "recording_detail.html",
        {
            "user": user,
            "recording": recording,
            "owner": recording.owner,
            "analysis": analysis_data,
            "duration": duration,
            "can_download": user.role == UserRole.admin and file_path.exists(),
        },
    )


@app.get("/recording/{recording_id}/download")
def download_recording(
    recording_id: int,
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    recording = db.query(Recording).filter(Recording.id == recording_id).first()
    if not recording:
        raise HTTPException(status_code=404, detail="Запись не найдена")

    file_path = Path(recording.stored_path)
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Файл записи не найден на диске")

    return FileResponse(
        path=file_path,
        filename=recording.filename,
        media_type="application/octet-stream",
    )


@app.post("/recording/{recording_id}/ask")
async def ask_recording_ai(
    recording_id: int,
    question: str = Form(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    recording = db.query(Recording).filter(Recording.id == recording_id).first()
    if not recording or not can_access_recording(user, recording.user_id):
        raise HTTPException(status_code=404, detail="Запись не найдена")

    if recording.status != RecordingStatus.done or not recording.transcript:
        raise HTTPException(status_code=400, detail="Анализ ещё не готов")

    question = question.strip()
    if not question or len(question) > 1000:
        raise HTTPException(status_code=400, detail="Введите вопрос (до 1000 символов)")

    summary = recording.analysis.summary if recording.analysis else ""
    try:
        answer = await run_in_threadpool(
            ask_about_recording,
            recording.transcript,
            summary,
            question,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return JSONResponse({"answer": answer})


@app.post("/recording/{recording_id}/retry")
def retry_analysis(
    recording_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    recording = db.query(Recording).filter(Recording.id == recording_id).first()
    if not recording or not can_access_recording(user, recording.user_id):
        raise HTTPException(status_code=404, detail="Запись не найдена")

    recording.status = RecordingStatus.pending
    recording.error_message = None
    db.commit()
    schedule_analysis(recording.id)
    return RedirectResponse(f"/recording/{recording_id}", status_code=302)


@app.get("/admin/settings", response_class=HTMLResponse)
def admin_settings(request: Request, user: User = Depends(require_admin)):
    values = get_env_values()
    ok, status_message = openai_config_status()
    return templates.TemplateResponse(
        request,
        "admin_settings.html",
        {
            "user": user,
            "status_ok": ok,
            "status_message": status_message,
            "openai_masked": mask_key(values.get("OPENAI_API_KEY", "")),
            "groq_masked": mask_key(values.get("GROQ_API_KEY", "")),
            "deepseek_masked": mask_key(values.get("DEEPSEEK_API_KEY", "")),
            "demo_mode": values.get("DEMO_MODE", "true").lower() == "true",
            "saved": request.query_params.get("saved") == "1",
            "error": request.query_params.get("error"),
        },
    )


@app.post("/admin/settings")
def admin_settings_save(
    request: Request,
    openai_key: str = Form(""),
    groq_key: str = Form(""),
    deepseek_key: str = Form(""),
    demo_mode: str = Form("false"),
    user: User = Depends(require_admin),
):
    from urllib.parse import quote

    current = get_env_values()
    try:
        save_env_values(
            openai_key=openai_key.strip() or current.get("OPENAI_API_KEY", ""),
            groq_key=groq_key.strip() or current.get("GROQ_API_KEY", ""),
            deepseek_key=deepseek_key.strip() or current.get("DEEPSEEK_API_KEY", ""),
            demo_mode=demo_mode == "true",
        )
        load_dotenv(override=True)
    except Exception as exc:
        return RedirectResponse(f"/admin/settings?error={quote(str(exc))}", status_code=302)
    return RedirectResponse("/admin/settings?saved=1", status_code=302)


@app.get("/admin/managers", response_class=HTMLResponse)
def admin_managers(request: Request, user: User = Depends(require_admin), db: Session = Depends(get_db)):
    pending = (
        db.query(User)
        .filter(User.role == UserRole.manager, User.is_approved.is_(False))
        .order_by(User.created_at.desc())
        .all()
    )
    managers = (
        db.query(User)
        .filter(User.role == UserRole.manager, User.is_approved.is_(True))
        .order_by(User.full_name)
        .all()
    )
    manager_data = []
    for m in managers:
        count = db.query(func.count(Recording.id)).filter(Recording.user_id == m.id).scalar()
        avg = (
            db.query(func.avg(Analysis.total_score))
            .join(Recording)
            .filter(Recording.user_id == m.id)
            .scalar()
        )
        manager_data.append({"user": m, "count": count or 0, "avg_score": round(avg or 0, 1)})

    return templates.TemplateResponse(
        request,
        "admin_managers.html",
        {"user": user, "managers": manager_data, "pending": pending},
    )


@app.post("/admin/managers")
def create_manager(
    username: str = Form(...),
    password: str = Form(...),
    full_name: str = Form(...),
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    if db.query(User).filter(User.username == username).first():
        raise HTTPException(status_code=400, detail="Пользователь уже существует")

    manager = User(
        username=username,
        password_hash=hash_password(password),
        full_name=full_name,
        role=UserRole.manager,
        is_approved=True,
    )
    db.add(manager)
    db.commit()
    return RedirectResponse("/admin/managers", status_code=302)


@app.post("/admin/managers/{manager_id}/approve")
def approve_manager(
    manager_id: int,
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    manager = db.query(User).filter(User.id == manager_id, User.role == UserRole.manager).first()
    if not manager:
        raise HTTPException(status_code=404, detail="Менеджер не найден")
    manager.is_approved = True
    db.commit()
    return RedirectResponse("/admin/managers", status_code=302)


def remove_manager(db: Session, manager: User) -> None:
    for recording in db.query(Recording).filter(Recording.user_id == manager.id).all():
        try:
            path = Path(recording.stored_path)
            if path.is_file():
                path.unlink()
        except OSError:
            pass

    user_dir = UPLOADS_DIR / str(manager.id)
    if user_dir.is_dir():
        shutil.rmtree(user_dir, ignore_errors=True)

    db.delete(manager)
    db.commit()


@app.post("/admin/managers/{manager_id}/reject")
def reject_manager(
    manager_id: int,
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    manager = db.query(User).filter(User.id == manager_id, User.role == UserRole.manager).first()
    if not manager:
        raise HTTPException(status_code=404, detail="Менеджер не найден")
    remove_manager(db, manager)
    return RedirectResponse("/admin/managers", status_code=302)


@app.post("/admin/managers/{manager_id}/delete")
def delete_manager(
    manager_id: int,
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    manager = db.query(User).filter(User.id == manager_id, User.role == UserRole.manager).first()
    if not manager:
        raise HTTPException(status_code=404, detail="Менеджер не найден")
    if manager.id == user.id:
        raise HTTPException(status_code=400, detail="Нельзя удалить свой аккаунт")
    remove_manager(db, manager)
    return RedirectResponse("/admin/managers", status_code=302)


@app.get("/admin/manager/{manager_id}", response_class=HTMLResponse)
def admin_manager_detail(
    manager_id: int,
    request: Request,
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    manager = db.query(User).filter(User.id == manager_id, User.role == UserRole.manager).first()
    if not manager:
        raise HTTPException(status_code=404, detail="Менеджер не найден")

    recordings = (
        db.query(Recording)
        .filter(Recording.user_id == manager.id)
        .order_by(Recording.uploaded_at.desc())
        .all()
    )
    return templates.TemplateResponse(
        request,
        "admin_manager_detail.html",
        {
            "user": user,
            "manager": manager,
            "recordings": recordings,
            "stats": manager_stats(db, manager.id),
        },
    )