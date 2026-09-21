"""CLI: разбирает файл с обращениями и печатает категорию и черновик ответа.

    python -m app.cli messages.txt
"""

import argparse
import sys
from dataclasses import replace
from pathlib import Path

from app import db
from app.classifier import classify_many
from app.config import Settings, load_env_file
from app.llm import LLMClient
from app.messages import parse_messages


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m app.cli", description="Классификация обращений из файла."
    )
    parser.add_argument("file", nargs="?", default="messages.txt", help="файл: одно обращение на строку")
    parser.add_argument("--offline", action="store_true", help="не звать LLM, только правила")
    parser.add_argument("--no-save", action="store_true", help="не записывать результат в базу")
    parser.add_argument("--db", help="путь к базе SQLite (по умолчанию из DB_PATH)")
    args = parser.parse_args(argv)

    load_env_file(".env")
    settings = Settings.from_env()
    if args.db:
        settings = replace(settings, db_path=args.db)

    path = Path(args.file)
    if not path.is_file():
        print(f"Файл не найден: {path}", file=sys.stderr)
        return 2
    texts = parse_messages(path.read_text(encoding="utf-8"))
    if not texts:
        print(f"В файле нет обращений: {path}", file=sys.stderr)
        return 2

    llm = None
    if args.offline:
        pass
    elif settings.llm_configured:
        llm = LLMClient(settings)
    else:
        print("LLM_API_KEY не задан — классифицирую правилами.", file=sys.stderr)

    conn = db.connect(settings.db_path)
    try:
        db.init_db(conn)
        results = classify_many(texts, db.list_categories(conn), llm, settings.org_name)
        for number, (text, result) in enumerate(zip(texts, results), start=1):
            engine = f"llm: {result.model}" if result.engine == "llm" else "правила"
            print(f"[{number}/{len(texts)}] {text}")
            print(
                f"  Категория: {result.category['name']} "
                f"(уверенность {result.confidence:.0%}, {engine})"
            )
            print(f"  Черновик ответа: {result.draft_reply}")
            print()
            if not args.no_save:
                db.save_classification(conn, text, "cli", result)
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
