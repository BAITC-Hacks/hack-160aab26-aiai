from pathlib import Path

from app import db
from app.cli import main

ROOT = Path(__file__).resolve().parent.parent
MESSAGES = str(ROOT / "messages.txt")


def test_prints_category_and_draft_for_each_of_five_messages(tmp_path, capsys):
    code = main([MESSAGES, "--offline", "--db", str(tmp_path / "cli.db")])
    out = capsys.readouterr().out
    assert code == 0
    assert out.count("Категория:") == 5
    assert out.count("Черновик ответа:") == 5
    assert "[1/5] Как получить справку о месте учёбы?" in out
    assert "Категория: справка" in out
    assert "Категория: жалоба" in out
    assert "Категория: другое" in out


def test_results_are_saved_to_database_with_cli_source(tmp_path):
    db_path = tmp_path / "cli.db"
    main([MESSAGES, "--offline", "--db", str(db_path)])
    tickets = db.list_tickets(db.connect(db_path))
    assert len(tickets) == 5
    assert {t["source"] for t in tickets} == {"cli"}


def test_no_save_flag_leaves_database_empty(tmp_path):
    db_path = tmp_path / "cli.db"
    main([MESSAGES, "--offline", "--no-save", "--db", str(db_path)])
    assert db.list_tickets(db.connect(db_path)) == []


def test_missing_file_is_reported_with_exit_code_2(tmp_path, capsys):
    code = main([str(tmp_path / "nope.txt"), "--offline", "--db", str(tmp_path / "cli.db")])
    assert code == 2
    assert "nope.txt" in capsys.readouterr().err


def test_without_key_warns_that_rules_are_used(tmp_path, capsys, monkeypatch):
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.chdir(tmp_path)  # здесь нет .env
    main([MESSAGES, "--db", str(tmp_path / "cli.db")])
    assert "LLM_API_KEY" in capsys.readouterr().err
