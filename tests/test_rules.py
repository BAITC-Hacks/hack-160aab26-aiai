import pytest

from app.rules import classify_by_rules


@pytest.mark.parametrize(
    "text, expected",
    [
        ("Как получить справку о месте учёбы?", "справка"),
        ("В столовой очередь, еда холодная.", "жалоба"),
        ("Хочу записаться на консультацию завтра.", "другое"),
        ("Пропал Wi‑Fi в корпусе B.", "жалоба"),
        ("Где парковка для гостей?", "справка"),
    ],
)
def test_five_assignment_messages(categories, text, expected):
    assert classify_by_rules(text, categories).category["name"] == expected


def test_no_keyword_match_goes_to_fallback_category(categories):
    result = classify_by_rules("абракадабра", categories)
    assert result.category["is_fallback"]


def test_keyword_matches_only_at_word_start(categories):
    # «негде» содержит «где», но информационным вопросом не является
    result = classify_by_rules("Мне негде", categories)
    assert result.category["is_fallback"]


def test_yo_and_case_are_normalized(categories):
    result = classify_by_rules("ВСЁ СЛОМАЛОСЬ", categories)
    assert result.category["name"] == "жалоба"


def test_draft_reply_comes_from_category_fallback_reply(categories):
    result = classify_by_rules("Пропал интернет", categories)
    assert result.draft_reply == result.category["fallback_reply"]
    assert result.draft_reply.strip()


def test_result_is_marked_as_rules_engine(categories):
    result = classify_by_rules("Где парковка?", categories)
    assert result.engine == "rules"
    assert result.model is None
