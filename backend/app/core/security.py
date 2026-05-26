import re
import secrets
from hashlib import sha256


def make_run_id() -> str:
    return secrets.token_urlsafe(12)


def hash_prompt(prompt: str, base_url: str | None, prompt_version: str) -> str:
    payload = f"{prompt_version}|{base_url or ''}|{prompt.strip()}".encode("utf-8")
    return sha256(payload).hexdigest()


def safe_session_name(name: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9_.-]+", "-", name.strip()).strip("-")
    return cleaned[:64] or f"session-{secrets.token_hex(4)}"

