"""Хранилище на SQLite: категории и обращения."""

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS categories (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    name           TEXT NOT NULL,
    description    TEXT NOT NULL DEFAULT '',
    reply_hint     TEXT NOT NULL DEFAULT '',
    keywords       TEXT NOT NULL DEFAULT '',
    fallback_reply TEXT NOT NULL DEFAULT '',
    is_fallback    INTEGER NOT NULL DEFAULT 0,
    is_active      INTEGER NOT NULL DEFAULT 1,
    created_at     TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS tickets (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    text        TEXT NOT NULL,
    source      TEXT NOT NULL DEFAULT 'web',
    category_id INTEGER NOT NULL REFERENCES categories(id),
    confidence  REAL NOT NULL,
    reason      TEXT NOT NULL DEFAULT '',
    draft_reply TEXT NOT NULL,
    engine      TEXT NOT NULL,
    model       TEXT,
    latency_ms  INTEGER NOT NULL DEFAULT 0,
    status      TEXT NOT NULL DEFAULT 'new',
    final_reply TEXT,
    created_at  TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_tickets_category ON tickets(category_id);
"""

DEFAULT_CATEGORIES = [
    {
        "name": "справка",
        "description": (
            "Информационный вопрос: как получить документ или услугу, где что находится, "
            "как что-то работает, часы работы, контакты."
        ),
        "reply_hint": (
            "Дайте короткую инструкцию или укажите, куда обратиться. Точных данных нет — "
            "не выдумывайте их, а предложите уточнить в профильном подразделении."
        ),
        "keywords": (
            "как получить, как оформить, как заказать, где, когда, сколько стоит, "
            "какие документы, справк, расписани, часы работы, подскажите"
        ),
        "fallback_reply": (
            "Здравствуйте! Спасибо за вопрос. Мы уточним информацию и ответим вам "
            "в ближайшее время."
        ),
        "is_fallback": 0,
    },
    {
        "name": "жалоба",
        "description": (
            "Сообщение о проблеме, сбое или недовольстве: что-то не работает, сломалось, "
            "пропало, плохое качество услуги, очереди, грубость."
        ),
        "reply_hint": (
            "Извинитесь за неудобства, подтвердите, что обращение зарегистрировано и передано "
            "ответственной службе, назовите следующий шаг. Не оправдывайтесь и не обещайте "
            "сроков, которых не знаете."
        ),
        "keywords": (
            "не работает, пропал, сломал, холодн, очеред, плохо, ужасн, грязн, жалоб, "
            "невозможно, безобрази, груб, хамств, течет, протека, нет воды, нет света"
        ),
        "fallback_reply": (
            "Здравствуйте! Приносим извинения за неудобства. Ваше обращение зарегистрировано "
            "и передано ответственной службе, мы сообщим о результате."
        ),
        "is_fallback": 0,
    },
    {
        "name": "другое",
        "description": (
            "Всё остальное: заявки и просьбы (записаться, забронировать), предложения, "
            "благодарности, сообщения без понятного запроса."
        ),
        "reply_hint": (
            "Подтвердите получение, уточните недостающие детали (дата, время, контакт) "
            "и сообщите, что с человеком свяжутся."
        ),
        "keywords": "",
        "fallback_reply": (
            "Здравствуйте! Ваше обращение получено. Сотрудник свяжется с вами, "
            "чтобы уточнить детали."
        ),
        "is_fallback": 1,
    },
]

CATEGORY_FIELDS = ("name", "description", "reply_hint", "keywords", "fallback_reply")
TICKET_FIELDS = ("final_reply", "status", "category_id")
TICKET_STATUSES = ("new", "answered")


class DuplicateCategory(ValueError):
    pass


class FallbackCategoryProtected(ValueError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def connect(path: str | Path) -> sqlite3.Connection:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    # Соединение живёт в рамках одного запроса, но FastAPI может выполнять зависимость
    # и обработчик в разных потоках пула.
    conn = sqlite3.connect(path, check_same_thread=False, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    if conn.execute("SELECT COUNT(*) FROM categories").fetchone()[0] == 0:
        for cat in DEFAULT_CATEGORIES:
            conn.execute(
                "INSERT INTO categories (name, description, reply_hint, keywords, "
                "fallback_reply, is_fallback, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (*(cat[f] for f in CATEGORY_FIELDS), cat["is_fallback"], _now()),
            )
    conn.commit()


# --- категории ---------------------------------------------------------------


def _category(row: sqlite3.Row) -> dict:
    cat = dict(row)
    cat["is_fallback"] = bool(cat["is_fallback"])
    cat["is_active"] = bool(cat["is_active"])
    return cat


def list_categories(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute("SELECT * FROM categories WHERE is_active = 1 ORDER BY id")
    return [_category(r) for r in rows]


def get_category(conn: sqlite3.Connection, category_id: int) -> dict | None:
    row = conn.execute("SELECT * FROM categories WHERE id = ?", (category_id,)).fetchone()
    return _category(row) if row else None


def _ensure_unique_name(conn: sqlite3.Connection, name: str, except_id: int | None = None):
    # lower() в SQLite не знает кириллицу, поэтому сравниваем в Python
    for cat in list_categories(conn):
        if cat["id"] != except_id and cat["name"].casefold() == name.casefold():
            raise DuplicateCategory(f"Категория «{cat['name']}» уже существует")


def create_category(
    conn: sqlite3.Connection,
    *,
    name: str,
    description: str = "",
    reply_hint: str = "",
    keywords: str = "",
    fallback_reply: str = "",
) -> dict:
    name = name.strip()
    _ensure_unique_name(conn, name)
    cur = conn.execute(
        "INSERT INTO categories (name, description, reply_hint, keywords, fallback_reply, "
        "created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (name, description, reply_hint, keywords, fallback_reply, _now()),
    )
    conn.commit()
    return get_category(conn, cur.lastrowid)


def update_category(conn: sqlite3.Connection, category_id: int, **fields) -> dict | None:
    if get_category(conn, category_id) is None:
        return None
    fields = {k: v for k, v in fields.items() if k in CATEGORY_FIELDS and v is not None}
    if "name" in fields:
        fields["name"] = fields["name"].strip()
        _ensure_unique_name(conn, fields["name"], except_id=category_id)
    if fields:
        assignments = ", ".join(f"{k} = ?" for k in fields)
        conn.execute(
            f"UPDATE categories SET {assignments} WHERE id = ?", (*fields.values(), category_id)
        )
        conn.commit()
    return get_category(conn, category_id)


def deactivate_category(conn: sqlite3.Connection, category_id: int) -> bool:
    """Скрывает категорию. Строка остаётся: на неё ссылаются прошлые обращения."""
    cat = get_category(conn, category_id)
    if cat is None:
        return False
    if cat["is_fallback"]:
        raise FallbackCategoryProtected(
            f"«{cat['name']}» — категория по умолчанию, её нельзя удалить"
        )
    conn.execute("UPDATE categories SET is_active = 0 WHERE id = ?", (category_id,))
    conn.commit()
    return True


# --- обращения ---------------------------------------------------------------

_TICKET_SELECT = (
    "SELECT t.*, c.name AS category FROM tickets t JOIN categories c ON c.id = t.category_id"
)


def get_ticket(conn: sqlite3.Connection, ticket_id: int) -> dict | None:
    row = conn.execute(f"{_TICKET_SELECT} WHERE t.id = ?", (ticket_id,)).fetchone()
    return dict(row) if row else None


def insert_ticket(
    conn: sqlite3.Connection,
    *,
    text: str,
    source: str,
    category_id: int,
    confidence: float,
    reason: str,
    draft_reply: str,
    engine: str,
    model: str | None,
    latency_ms: int,
) -> dict:
    cur = conn.execute(
        "INSERT INTO tickets (text, source, category_id, confidence, reason, draft_reply, "
        "engine, model, latency_ms, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (text, source, category_id, confidence, reason, draft_reply, engine, model,
         latency_ms, _now()),
    )
    conn.commit()
    return get_ticket(conn, cur.lastrowid)


def save_classification(conn: sqlite3.Connection, text: str, source: str, result) -> dict:
    """Сохраняет обращение вместе с итогом разбора (app.result.Classification)."""
    return insert_ticket(
        conn,
        text=text,
        source=source,
        category_id=result.category["id"],
        confidence=result.confidence,
        reason=result.reason,
        draft_reply=result.draft_reply,
        engine=result.engine,
        model=result.model,
        latency_ms=result.latency_ms,
    )


def list_tickets(
    conn: sqlite3.Connection,
    *,
    category_id: int | None = None,
    status: str | None = None,
    limit: int = 200,
) -> list[dict]:
    where, params = [], []
    if category_id is not None:
        where.append("t.category_id = ?")
        params.append(category_id)
    if status is not None:
        where.append("t.status = ?")
        params.append(status)
    clause = f" WHERE {' AND '.join(where)}" if where else ""
    rows = conn.execute(f"{_TICKET_SELECT}{clause} ORDER BY t.id DESC LIMIT ?", (*params, limit))
    return [dict(r) for r in rows]


def update_ticket(conn: sqlite3.Connection, ticket_id: int, **fields) -> dict | None:
    if get_ticket(conn, ticket_id) is None:
        return None
    fields = {k: v for k, v in fields.items() if k in TICKET_FIELDS and v is not None}
    if fields:
        assignments = ", ".join(f"{k} = ?" for k in fields)
        conn.execute(f"UPDATE tickets SET {assignments} WHERE id = ?", (*fields.values(), ticket_id))
        conn.commit()
    return get_ticket(conn, ticket_id)


def stats(conn: sqlite3.Connection) -> dict:
    by_category = conn.execute(
        "SELECT c.id, c.name, COUNT(t.id) AS count FROM categories c "
        "LEFT JOIN tickets t ON t.category_id = c.id "
        "GROUP BY c.id HAVING c.is_active = 1 OR COUNT(t.id) > 0 ORDER BY c.id"
    )
    by_engine = conn.execute("SELECT engine, COUNT(*) FROM tickets GROUP BY engine")
    answered = conn.execute("SELECT COUNT(*) FROM tickets WHERE status = 'answered'")
    categories = [dict(r) for r in by_category]
    return {
        "total": sum(c["count"] for c in categories),
        "answered": answered.fetchone()[0],
        "by_category": categories,
        "by_engine": {engine: count for engine, count in by_engine},
    }
