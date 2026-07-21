import json
import os
import re
import time
from pathlib import Path

from openai import OpenAI

from .api_http import API_TIMEOUT_SEC, get_api_http_client

from .ai_rules import load_ai_rules, load_reference_analysis, load_reference_excerpt
from .audio_prep import prepare_audio_chunks

WHISPER_PROMPT = "Росфинмониторинг, Госуслуги, Яндекс.Мессенджер, доверенность, МАКС."

WHISPER_ARTIFACTS = re.compile(
    r"(?:"
    r"Гоуслуги,\s*дроперство,\s*нотариус,\s*скриншот,\s*Рустор,\s*(?:Google Play|Гоogle Play)|"
    r"Гоула?\s*Мессенджер,\s*специалист,\s*дроперство,\s*нотариус,\s*скриншот,\s*Рустор,\s*Google Play|"
    r"Рустор,\s*Гоугл\s*Плей|"
    r"ПРОИНФОРМИРОН|"
    r"Гоу\s*Гоу\s*Гоу|"
    r"Гоусуслунгами|"
    r"Гоула\s*Плей|"
    r"Продолжение\s+следует\.\.\."
    r")",
    re.IGNORECASE,
)


def clean_transcript(text: str) -> str:
    cleaned = WHISPER_ARTIFACTS.sub(" ", text or "")
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned

PLACEHOLDER_API_KEYS = {
    "ваш_ключ_openai",
    "your_openai_api_key_here",
    "sk-your-key-here",
    "replace_me",
}

AUDIO_EXTENSIONS = {".mp3", ".wav", ".m4a", ".ogg", ".flac", ".webm", ".mp4", ".aac"}
TEXT_EXTENSIONS = {".txt", ".md", ".doc", ".docx", ".rtf", ".srt", ".vtt"}


def detect_file_type(filename: str, content_type: str = "") -> str:
    ext = Path(filename).suffix.lower()
    if ext in AUDIO_EXTENSIONS:
        return "audio"
    if ext in TEXT_EXTENSIONS:
        return "text"
    mime = (content_type or "").split(";")[0].strip().lower()
    if mime.startswith("audio/") or mime in ("video/mp4", "video/webm"):
        return "audio"
    if mime.startswith("text/"):
        return "text"
    return "unknown"


def read_text_file(path: Path) -> str:
    for encoding in ("utf-8", "cp1251", "latin-1"):
        try:
            return path.read_text(encoding=encoding)
        except UnicodeDecodeError:
            continue
    return path.read_text(encoding="utf-8", errors="ignore")


def _clean_key(name: str) -> str:
    value = (os.getenv(name) or "").strip()
    if not value or value.lower() in PLACEHOLDER_API_KEYS or not value.isascii():
        return ""
    return value


def has_openai_key() -> bool:
    key = _clean_key("OPENAI_API_KEY")
    return bool(key.startswith("sk-"))


def has_groq_key() -> bool:
    key = _clean_key("GROQ_API_KEY")
    return bool(key.startswith("gsk_"))


def has_deepseek_key() -> bool:
    key = _clean_key("DEEPSEEK_API_KEY")
    return bool(key.startswith("sk-"))


def prefer_groq_deepseek() -> bool:
    return has_groq_key() and has_deepseek_key()


def is_api_quota_error(exc: Exception) -> bool:
    text = str(exc).lower()
    return any(
        marker in text
        for marker in (
            "insufficient_quota",
            "exceeded your current quota",
            "rate limit",
            "429",
            "402",
            "billing",
            "rpm",
        )
    )


def is_auth_error(exc: Exception) -> bool:
    """Неверный/просроченный API-ключ — ретраи бессмысленны."""
    text = str(exc).lower()
    status = getattr(exc, "status_code", None)
    if status in (401, 403):
        return True
    return any(
        marker in text
        for marker in (
            "401",
            "403",
            "unauthorized",
            "authentication",
            "invalid api key",
            "incorrect api key",
            "invalid_api_key",
            "permission denied",
        )
    )


def is_connection_error(exc: Exception) -> bool:
    text = str(exc).lower()
    return any(
        marker in text
        for marker in (
            "connection error",
            "connecterror",
            "certificate_verify_failed",
            "timed out",
            "timeout",
            "connection reset",
        )
    )


def is_retriable_error(exc: Exception) -> bool:
    # 401/403 не ретраим — иначе засыпаем OpenAI 429-ретраями после мёртвого DeepSeek
    if is_auth_error(exc):
        return False
    return is_connection_error(exc) or is_api_quota_error(exc)


def _provider_error(provider: str, exc: Exception) -> RuntimeError:
    if is_auth_error(exc):
        return RuntimeError(
            f"{provider}: неверный или просроченный API-ключ (401). "
            f"Обновите ключ в .env / Настройках админа."
        )
    if is_api_quota_error(exc):
        return RuntimeError(
            f"{provider}: лимит/квота исчерпаны (429). "
            f"Подождите или смените ключ / тариф."
        )
    msg = str(exc).strip() or exc.__class__.__name__
    return RuntimeError(f"{provider}: {msg[:400]}")


def is_demo_mode() -> bool:
    if has_openai_key() or (has_groq_key() and has_deepseek_key()):
        return False
    demo_flag = (os.getenv("DEMO_MODE") or "true").strip().lower()
    return demo_flag not in ("0", "false", "no", "off")


def openai_config_status() -> tuple[bool, str]:
    if is_demo_mode():
        return True, "Демо-режим: анализ без ИИ (для теста интерфейса)"
    if has_groq_key() and has_deepseek_key():
        return True, "Реальный анализ: Groq (речь) + DeepSeek/Groq LLM (отчёт), очередь для ~20 человек"
    if has_groq_key():
        return True, "Реальный анализ: Groq (транскрипция + LLM-отчёт)"
    if has_openai_key():
        return True, "OpenAI API ключ настроен"
    if has_deepseek_key():
        return False, "Задан DEEPSEEK_API_KEY, но нет GROQ_API_KEY для транскрипции аудио"
    return False, "Не заданы API-ключи — добавьте GROQ_API_KEY (и желательно DEEPSEEK_API_KEY) в .env"


def get_openai_client() -> OpenAI:
    api_key = _clean_key("OPENAI_API_KEY")
    if not api_key.startswith("sk-"):
        raise RuntimeError(
            "Не задан OPENAI_API_KEY. Добавьте ключ в .env или используйте GROQ_API_KEY + DEEPSEEK_API_KEY"
        )
    # max_retries=1: при 429 не долбим API десятками повторов (главный источник «вечных» ошибок)
    return OpenAI(
        api_key=api_key,
        http_client=get_api_http_client(),
        timeout=API_TIMEOUT_SEC,
        max_retries=1,
    )


def get_groq_client() -> OpenAI:
    api_key = _clean_key("GROQ_API_KEY")
    if not api_key.startswith("gsk_"):
        raise RuntimeError("Не задан GROQ_API_KEY для транскрипции аудио")
    return OpenAI(
        api_key=api_key,
        base_url="https://api.groq.com/openai/v1",
        http_client=get_api_http_client(),
        timeout=API_TIMEOUT_SEC,
        max_retries=2,
    )


def get_deepseek_client() -> OpenAI:
    api_key = _clean_key("DEEPSEEK_API_KEY")
    if not api_key.startswith("sk-"):
        raise RuntimeError("Не задан DEEPSEEK_API_KEY для анализа разговоров")
    return OpenAI(
        api_key=api_key,
        base_url="https://api.deepseek.com",
        http_client=get_api_http_client(),
        timeout=API_TIMEOUT_SEC,
        max_retries=1,
    )


def _transcribe_with_client(client: OpenAI, model: str, path: Path, mime: str) -> str:
    chunks = prepare_audio_chunks(path)
    texts: list[str] = []
    for index, chunk in enumerate(chunks, start=1):
        # Для mp3-чанков всегда audio/mpeg; иначе API может отвергнуть файл
        chunk_mime = "audio/mpeg" if chunk.suffix.lower() == ".mp3" else mime
        upload_name = chunk.name if len(chunks) == 1 else f"{path.stem}_part{index}.mp3"
        last_exc: Exception | None = None
        for attempt in range(3):
            try:
                with chunk.open("rb") as audio_file:
                    result = client.audio.transcriptions.create(
                        model=model,
                        file=(upload_name, audio_file, chunk_mime),
                        language="ru",
                        prompt=WHISPER_PROMPT,
                        temperature=0,
                    )
                text = (result.text or "").strip()
                if text:
                    texts.append(text)
                last_exc = None
                break
            except Exception as exc:
                last_exc = exc
                if attempt < 2 and is_retriable_error(exc) and not is_auth_error(exc):
                    time.sleep(min(2 ** attempt, 15))
                    continue
                raise
        if last_exc:
            raise last_exc
    return clean_transcript("\n".join(texts).strip())


def transcribe_audio(path: Path) -> str:
    mime = {
        ".mp3": "audio/mpeg",
        ".wav": "audio/wav",
        ".m4a": "audio/mp4",
        ".ogg": "audio/ogg",
        ".flac": "audio/flac",
        ".webm": "audio/webm",
        ".mp4": "audio/mp4",
        ".aac": "audio/aac",
    }.get(path.suffix.lower(), "audio/mpeg")

    errors: list[Exception] = []

    # Основной путь: Groq (работает). OpenAI whisper — только если нет Groq.
    if has_groq_key():
        try:
            return _transcribe_with_client(get_groq_client(), "whisper-large-v3", path, mime)
        except Exception as exc:
            if prefer_groq_deepseek() and not is_connection_error(exc):
                raise _provider_error("Groq (транскрипция)", exc) from exc
            errors.append(_provider_error("Groq (транскрипция)", exc))

    if has_openai_key() and not prefer_groq_deepseek():
        try:
            return _transcribe_with_client(get_openai_client(), "whisper-1", path, mime)
        except Exception as exc:
            errors.append(_provider_error("OpenAI Whisper", exc))

    if errors:
        raise errors[-1]

    raise RuntimeError("Нет ключа для транскрипции аудио (OpenAI или Groq)")


def _build_analysis_prompt(transcript: str) -> str:
    rules = load_ai_rules()
    reference = load_reference_excerpt()
    analysis_example = load_reference_analysis()
    reference_block = ""
    if reference:
        reference_block += f"""
ЭТАЛОН ПРАВИЛЬНОЙ ТРАНСКРИПЦИИ (стиль и термины — как в учебных записях Edik):
---
{reference}
---
"""
    if analysis_example:
        reference_block += f"""
ЭТАЛОН ПРАВИЛЬНОГО АНАЛИЗА (формат JSON, оценки с цитатами):
---
{analysis_example}
---
"""
    return f"""Ты — эксперт контроля качества телефонных разговоров операторов (2 этап).

ПРАВИЛА (обязательно):
{rules}
{reference_block}
ТРАНСКРИПТ РАЗГОВОРА (единственный источник фактов):
---
{transcript}
---

Анализируй ВЕСЬ транскрипт от начала до конца. Не выдумывай фразы и события.

Верни ТОЛЬКО валидный JSON:
{{
  "sections": {{
    "needs_discovery": "Выявление потребностей: что оператор выяснил у клиента (только по фактам из записи)",
    "communication": "Общение: как оператор объяснял, ясность, тон (только по фактам)",
    "objection_handling": "Отработка возражений: как отвечал на вопросы и сомнения",
    "outcome": "Итог: к чему пришли в разговоре",
    "next_step": "Следующий шаг: что должен сделать клиент или оператор дальше"
  }},
  "errors": [
    {{
      "title": "краткое название",
      "quote": "точная цитата из транскрипта — обязательно",
      "explanation": "что не так",
      "reason": "почему это ошибка",
      "better_response": "как лучше (без выдуманных цитат клиента)"
    }}
  ],
  "missed_opportunities": ["упущение — только если видно из транскрипта"],
  "script_violations": ["нарушение регламента — с опорой на текст"],
  "weak_communication": ["слабое место — с опорой на текст"],
  "scores": {{
    "needs_discovery": 0-100,
    "communication": 0-100,
    "objection_handling": 0-100,
    "outcome": 0-100,
    "next_step": 0-100
  }},
  "total_score": 0-100,
  "summary": "краткий итог разговора (2-4 предложения, только факты из записи)",
  "recommendations": ["конкретная рекомендация оператору"]
}}

Запрещено: списки «правильные/неправильные фразы» без цитат; пересказ диалога в конце; оценки без опоры на транскрипт.
Если ошибок нет — errors: [], но sections и scores заполни."""


def _analyze_with_client(client: OpenAI, model: str, transcript: str) -> dict:
    last_exc: Exception | None = None
    # Лимит текста: слишком длинный prompt + эталоны → таймауты/ошибки на free PA
    text = (transcript or "").strip()
    if len(text) > 48000:
        text = text[:48000] + "\n…[транскрипт обрезан для анализа]"

    for attempt in range(3):
        try:
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "Ты анализируешь телефонные разговоры операторов. "
                            "Отвечай только JSON. Не выдумывай то, чего нет в транскрипте. "
                            "Учитывай весь текст транскрипта целиком."
                        ),
                    },
                    {"role": "user", "content": _build_analysis_prompt(text)},
                ],
                temperature=0.2,
                response_format={"type": "json_object"},
            )
            content = response.choices[0].message.content or "{}"
            return json.loads(content)
        except Exception as exc:
            last_exc = exc
            if is_auth_error(exc):
                raise
            if attempt < 2 and is_retriable_error(exc):
                time.sleep(min(2 ** attempt, 12))
                continue
            raise
    if last_exc:
        raise last_exc
    return {}


def analyze_transcript(transcript: str) -> dict:
    """Анализ текста: DeepSeek → Groq LLM → OpenAI.

    Важно для 20+ человек: если DeepSeek 401/квота — не роняем всех,
    уходим на Groq (тот же ключ, что и для Whisper).
    """
    errors: list[Exception] = []

    if has_deepseek_key():
        try:
            return _analyze_with_client(get_deepseek_client(), "deepseek-chat", transcript)
        except Exception as exc:
            # 401/429 — пробуем следующий провайдер, не блокируем всю команду
            errors.append(_provider_error("DeepSeek (анализ)", exc))
            print(f"[analyze] DeepSeek fail → fallback: {exc}", flush=True)

    if has_groq_key():
        # Качественная модель, затем быстрая (лимиты free tier)
        for model in ("llama-3.3-70b-versatile", "llama-3.1-8b-instant"):
            try:
                return _analyze_with_client(get_groq_client(), model, transcript)
            except Exception as exc:
                errors.append(_provider_error(f"Groq/{model}", exc))
                print(f"[analyze] Groq {model} fail: {exc}", flush=True)
                if is_auth_error(exc):
                    break
                continue

    if has_openai_key():
        try:
            return _analyze_with_client(get_openai_client(), "gpt-4o-mini", transcript)
        except Exception as exc:
            errors.append(_provider_error("OpenAI (анализ)", exc))

    if errors:
        # Самая полезная ошибка: не «OpenAI 429», а первая реальная (часто DeepSeek 401)
        raise errors[0]

    raise RuntimeError("Нет ключа для анализа разговоров (DeepSeek / Groq / OpenAI)")


CHAT_PROMPT = """Ты — ИИ-помощник по контролю качества разговоров операторов.
Отвечай только на основе транскрипта. Не выдумывай фразы, которых не было в записи.
Помогай сотруднику понять анализ и улучшить навыки общения.

Транскрипт разговора:
---
{transcript}
---

Краткое резюме анализа:
{summary}

Вопрос сотрудника:
{question}

Ответь по-русски, конкретно и дружелюбно. Давай практические советы и примеры фраз.
Если вопрос не связан с разговором — вежливо перенаправь к теме анализа."""


def ask_about_recording(transcript: str, summary: str, question: str) -> str:
    if is_demo_mode():
        return demo_chat_answer(question)

    prompt = CHAT_PROMPT.format(
        transcript=(transcript or "")[:15000],
        summary=summary or "Резюме не предоставлено",
        question=question.strip(),
    )
    messages = [
        {"role": "system", "content": "Ты помогаешь сотрудникам улучшать телефонные разговоры."},
        {"role": "user", "content": prompt},
    ]
    candidates: list[tuple[OpenAI, str]] = []
    if has_deepseek_key():
        candidates.append((get_deepseek_client(), "deepseek-chat"))
    if has_groq_key():
        candidates.append((get_groq_client(), "llama-3.3-70b-versatile"))
        candidates.append((get_groq_client(), "llama-3.1-8b-instant"))
    if has_openai_key():
        candidates.append((get_openai_client(), "gpt-4o-mini"))
    if not candidates:
        raise RuntimeError("Нет ключа для чата с ИИ")

    last_exc: Exception | None = None
    for client, model in candidates:
        try:
            response = client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=0.5,
            )
            return (response.choices[0].message.content or "Не удалось получить ответ").strip()
        except Exception as exc:
            last_exc = exc
            continue
    if last_exc:
        raise _provider_error("Чат с ИИ", last_exc)
    raise RuntimeError("Не удалось получить ответ ИИ")


DEMO_TRANSCRIPT = """Менеджер: Добрый день, компания «Профи», меня зовут Алексей. Чем могу помочь?
Клиент: Здравствуйте, я смотрел ваш курс, хочу уточнить условия.
Менеджер: Отлично. Расскажите, что именно вас интересует?
Клиент: Сколько длится программа и можно ли в рассрочку?
Менеджер: Программа на 8 недель, рассрочка есть на 3 и 6 месяцев.
Клиент: А если не подойдёт, можно вернуть деньги?
Менеджер: Ну, возврат обычно не делаем, но у нас хороший курс, вам понравится.
Клиент: Мне нужно подумать, перезвоните завтра.
Менеджер: Хорошо, до свидания."""


def demo_analysis() -> dict:
    return {
        "errors": [
            {
                "title": "Слабая отработка возражения о возврате",
                "explanation": "Менеджер ответил уклончиво и не объяснил условия гарантии",
                "reason": "Клиент не получил уверенности и закрыл разговор без решения",
                "better_response": "Кратко описать политику возврата и предложить пробный модуль",
                "example_phrase": "В течение 7 дней вы можете вернуть оплату, если формат не подойдёт — давайте я расскажу, как это работает.",
            },
            {
                "title": "Нет фиксации следующего шага",
                "explanation": "Разговор завершился фразой «перезвоните завтра» без конкретного времени",
                "reason": "Вероятность повторного контакта снижается",
                "better_response": "Согласовать точное время звонка и отправить материалы в мессенджер",
                "example_phrase": "Давайте созвонимся завтра в 11:00, а сейчас пришлю программу и отзывы в WhatsApp.",
            },
        ],
        "missed_opportunities": [
            "Не уточнил, какой именно курс смотрел клиент",
            "Не выявил главную цель обучения клиента",
        ],
        "script_violations": [
            "Пропущен блок презентации выгод",
            "Не использована техника уточняющих вопросов после цены",
        ],
        "weak_communication": [
            "Мало эмпатии в ответе на сомнения клиента",
            "Завершение разговора без резюме договорённостей",
        ],
        "scores": {
            "script_compliance": 62,
            "objection_handling": 48,
            "needs_discovery": 55,
            "argumentation": 58,
            "call_closing": 40,
        },
        "total_score": 53,
        "summary": "Менеджер корректно представился и ответил на базовые вопросы, но слабо отработал возражение о возврате и не зафиксировал следующий шаг. Разговор завершился без договорённости.",
        "recommendations": [
            "Отрабатывать возражения по схеме: признание → уточнение → аргумент → проверка",
            "Всегда фиксировать дату и время следующего контакта",
            "Задавать минимум 3 вопроса на выявление потребности до презентации цены",
        ],
    }


def demo_chat_answer(question: str) -> str:
    q = question.lower()
    if "возраж" in q or "возврат" in q:
        return (
            "На возражение о возврате лучше отвечать спокойно и конкретно: назовите срок, "
            "условия и предложите безопасный следующий шаг — например, демо-урок. "
            "Фраза: «Понимаю ваши сомнения. У нас есть 7 дней на возврат — давайте я объясню, как это работает»."
        )
    if "закрыт" in q or "следующ" in q:
        return (
            "В конце звонка обязательно резюмируйте договорённости и назначьте точное время. "
            "Пример: «Итого: отправляю программу сейчас, завтра в 11:00 созваниваемся и решаем по оплате»."
        )
    return (
        "В этом разговоре главная зона роста — работа с возражениями и фиксация следующего шага. "
        "Сфокусируйтесь на уточняющих вопросах после сомнений клиента и завершайте звонок "
        "с конкретной договорённостью, а не с «я подумаю»."
    )


def process_recording_file(path: Path, file_type: str) -> tuple[str, dict]:
    if is_demo_mode():
        if file_type == "text":
            transcript = read_text_file(path).strip() or DEMO_TRANSCRIPT
        else:
            transcript = DEMO_TRANSCRIPT
        return transcript, demo_analysis()

    if file_type == "audio":
        transcript = transcribe_audio(path)
    else:
        transcript = read_text_file(path).strip()

    if not transcript:
        raise RuntimeError("Файл пустой или не удалось получить текст разговора")

    analysis = analyze_transcript(transcript)
    return transcript, analysis