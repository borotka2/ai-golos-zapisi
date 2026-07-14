from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
RULES_PATH = DATA_DIR / "ai_rules.txt"
REFERENCE_DIR = DATA_DIR / "reference"

REFERENCE_TRANSCRIPTS = (
    "etalon_dlinny_transcript.txt",
    "etalon_korotky_transcript.txt",
)
REFERENCE_ANALYSIS = REFERENCE_DIR / "etalon_analysis_example.json"


def load_ai_rules() -> str:
    if RULES_PATH.exists():
        return RULES_PATH.read_text(encoding="utf-8").strip()
    return ""


def load_reference_excerpt(max_chars: int = 1200) -> str:
    parts: list[str] = []
    remaining = max_chars
    for name in REFERENCE_TRANSCRIPTS:
        path = REFERENCE_DIR / name
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8").strip()
        if not text:
            continue
        chunk = text[:remaining]
        if chunk:
            parts.append(f"[{name}]\n{chunk}")
            remaining -= len(chunk)
        if remaining <= 0:
            break
    return "\n\n".join(parts)


def load_reference_analysis(max_chars: int = 1200) -> str:
    if not REFERENCE_ANALYSIS.exists():
        return ""
    return REFERENCE_ANALYSIS.read_text(encoding="utf-8").strip()[:max_chars]