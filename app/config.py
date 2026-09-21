"""Настройки из переменных окружения (и из .env, если он лежит рядом)."""

import os
from collections.abc import MutableMapping
from dataclasses import dataclass, fields
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    llm_api_key: str = ""
    llm_base_url: str = "https://api.openai.com/v1"
    llm_model: str = "gpt-5-mini"
    llm_timeout: float = 45.0
    llm_reasoning_effort: str = ""
    org_name: str = "учебное заведение"
    db_path: str = "data/app.db"
    messages_path: str = "messages.txt"

    @property
    def llm_configured(self) -> bool:
        return bool(self.llm_api_key)

    @classmethod
    def from_env(cls, env: MutableMapping[str, str] | None = None) -> "Settings":
        env = os.environ if env is None else env
        values = {}
        for field in fields(cls):
            raw = env.get(field.name.upper(), "").strip()
            if raw:  # пустое значение = «не задано», берём значение по умолчанию
                values[field.name] = float(raw) if field.type is float else raw
        if "llm_base_url" in values:
            values["llm_base_url"] = values["llm_base_url"].rstrip("/")
        return cls(**values)


def load_env_file(path: str | Path, env: MutableMapping[str, str] | None = None) -> None:
    """Подкладывает KEY=VALUE из файла в окружение, не перетирая уже заданное."""
    env = os.environ if env is None else env
    path = Path(path)
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        env.setdefault(key.strip(), value.strip().strip("'\""))
