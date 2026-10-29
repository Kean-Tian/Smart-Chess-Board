"""Private local key storage, excluded from Git."""
import os
from pathlib import Path
import tempfile

from openrouter_engine import OpenRouterError, validate_api_key

KEY_FILE = Path(__file__).resolve().parents[1] / ".openrouter-key"


def load_api_key():
    try:
        value = KEY_FILE.read_text(encoding="ascii").strip()
    except FileNotFoundError:
        return ""
    except (OSError, UnicodeError) as exc:
        raise OpenRouterError("Cannot read the saved OpenRouter key. Use --set-api-key to replace it.",
                              retryable=False) from exc
    return validate_api_key(value) if value else ""


def save_api_key(value):
    key = validate_api_key(value)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="ascii", dir=KEY_FILE.parent,
                                         prefix=".openrouter-key.", delete=False) as output:
            temporary = Path(output.name)
            os.fchmod(output.fileno(), 0o600)
            output.write(key + "\n")
        os.replace(temporary, KEY_FILE)
    except OSError as exc:
        raise OpenRouterError("Cannot save the OpenRouter key locally. Check project directory permissions.",
                              retryable=False) from exc
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
