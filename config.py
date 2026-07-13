from dataclasses import dataclass
from pathlib import Path
import os
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent

@dataclass(frozen=True)
class Settings:
    url: str
    db: str
    login: str
    api_key: str
    output_dir: Path
    log_dir: Path

def load_settings() -> Settings:
    load_dotenv(BASE_DIR / ".env")
    values = {
        "url": os.getenv("ODOO_URL", "").strip().rstrip("/"),
        "db": os.getenv("ODOO_DB", "").strip(),
        "login": os.getenv("ODOO_LOGIN", "").strip(),
        "api_key": os.getenv("ODOO_API_KEY", "").strip(),
    }
    missing = [k for k, v in values.items() if not v]
    if missing:
        raise ValueError("Neužpildyti .env laukai: " + ", ".join(missing))
    output_dir = BASE_DIR / "output"
    log_dir = BASE_DIR / "logs"
    output_dir.mkdir(exist_ok=True)
    log_dir.mkdir(exist_ok=True)
    return Settings(**values, output_dir=output_dir, log_dir=log_dir)