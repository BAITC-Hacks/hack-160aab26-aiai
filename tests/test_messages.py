from pathlib import Path

from app.messages import parse_messages

ROOT = Path(__file__).resolve().parent.parent


def test_strips_leading_numbering():
    assert parse_messages("1) Где парковка?\n2. Пропал Wi-Fi") == [
        "Где парковка?",
        "Пропал Wi-Fi",
    ]


def test_skips_blank_lines_and_trims_spaces():
    assert parse_messages("\n  Первое  \n\n\nВторое\n") == ["Первое", "Второе"]


def test_keeps_numbers_that_are_part_of_the_text():
    assert parse_messages("3 дня нет отопления") == ["3 дня нет отопления"]


def test_repo_messages_file_has_five_messages():
    messages = parse_messages((ROOT / "messages.txt").read_text(encoding="utf-8"))
    assert len(messages) == 5
    assert messages[0] == "Как получить справку о месте учёбы?"
