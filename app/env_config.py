import os
import re
from pathlib import Path

ROOT = Path(__file__).parent.parent
ENV_PATH = ROOT / ".env"
OLEG_KEYS = Path(r"C:\Users\Edik\Desktop\oleg\data\keys.env")

SK_PATTERN = re.compile(r"sk-[a-zA-Z0-9_-]{20,}")
GSK_PATTERN = re.compile(r"gsk_[a-zA-Z0-9_-]{20,}")


def _parse_env_file(path: Path) -> dict[str, str]:
    data: dict[str, str] = {}
    if not path.exists():
        return data
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        data[key.strip()] = value.strip()
    return data


def mask_key(value: str) -> str:
    value = (value or "").strip()
    if len(value) <= 8:
        return "не задан"
    return f"{value[:6]}...{value[-4:]}"


def get_env_values() -> dict[str, str]:
    values = _parse_env_file(ENV_PATH)
    if not values.get("GROQ_API_KEY") or not values.get("DEEPSEEK_API_KEY"):
        oleg = _parse_env_file(OLEG_KEYS)
        values.setdefault("GROQ_API_KEY", oleg.get("GROQ_API_KEY", ""))
        values.setdefault("DEEPSEEK_API_KEY", oleg.get("DEEPSEEK_API_KEY", ""))
        values.setdefault("OPENAI_API_KEY", oleg.get("OPENAI_API_KEY", ""))
    return values


def save_env_values(
    *,
    openai_key: str | None = None,
    groq_key: str | None = None,
    deepseek_key: str | None = None,
    demo_mode: bool = False,
) -> None:
    current = get_env_values()
    if openai_key is not None:
        current["OPENAI_API_KEY"] = openai_key.strip()
    if groq_key is not None:
        current["GROQ_API_KEY"] = groq_key.strip()
    if deepseek_key is not None:
        current["DEEPSEEK_API_KEY"] = deepseek_key.strip()

    current["DEMO_MODE"] = "false" if not demo_mode else "true"
    current.setdefault("SECRET_KEY", "ai-golos-local-secret-8f3c2a91b7e4")

    lines = [
        f"DEMO_MODE={current['DEMO_MODE']}",
        f"OPENAI_API_KEY={current.get('OPENAI_API_KEY', '')}",
        f"GROQ_API_KEY={current.get('GROQ_API_KEY', '')}",
        f"DEEPSEEK_API_KEY={current.get('DEEPSEEK_API_KEY', '')}",
        f"SECRET_KEY={current['SECRET_KEY']}",
    ]
    ENV_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")

    for key in ("OPENAI_API_KEY", "GROQ_API_KEY", "DEEPSEEK_API_KEY", "DEMO_MODE"):
        os.environ[key] = current.get(key, "")


def auto_import_keys() -> bool:
    values = get_env_values()
    if values.get("GROQ_API_KEY") and values.get("DEEPSEEK_API_KEY"):
        save_env_values(
            openai_key=values.get("OPENAI_API_KEY", ""),
            groq_key=values.get("GROQ_API_KEY", ""),
            deepseek_key=values.get("DEEPSEEK_API_KEY", ""),
            demo_mode=False,
        )
        return True
    return False