import hashlib
import json
from pathlib import Path

_USERS_FILE = Path(__file__).parent / "users.json"
_DEFAULT_USER = "admin"
_DEFAULT_PASSWORD = "admin123"


def _hash(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()


def load_users() -> dict[str, str]:
    if not _USERS_FILE.exists():
        return {}
    try:
        return json.loads(_USERS_FILE.read_text())
    except Exception:
        return {}


def _save_users(users: dict[str, str]) -> None:
    _USERS_FILE.write_text(json.dumps(users, indent=2))


def create_user(username: str, password: str) -> None:
    """Add or update a user with a hashed password."""
    users = load_users()
    users[username] = _hash(password)
    _save_users(users)


def authenticate(username: str, password: str) -> bool:
    """Gradio auth callback. Bootstraps a default admin account on first run."""
    users = load_users()
    if not users:
        print(f"\n[auth] No users found — creating default account: {_DEFAULT_USER} / {_DEFAULT_PASSWORD}")
        print("[auth] Change this password by editing users.json!\n")
        create_user(_DEFAULT_USER, _DEFAULT_PASSWORD)
        users = load_users()
    return users.get(username) == _hash(password)
