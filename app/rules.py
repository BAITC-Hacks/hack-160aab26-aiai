"""Запасной классификатор на ключевых словах — работает, когда LLM недоступна."""

import re

from app.result import Classification

DEFAULT_REPLY = "Здравствуйте! Ваше обращение получено, мы ответим в ближайшее время."


def _normalize(text: str) -> str:
    return text.lower().replace("ё", "е")


def _keywords(category: dict) -> list[str]:
    return [k for k in (_normalize(k).strip() for k in category["keywords"].split(",")) if k]


def _matches(text: str, keyword: str) -> bool:
    # Ключ — начало слова: «справк» ловит «справку», но «где» не ловит «негде»
    return re.search(rf"(?<!\w){re.escape(keyword)}", text) is not None


def classify_by_rules(text: str, categories: list[dict]) -> Classification:
    normalized = _normalize(text)
    best, best_hits = None, []
    for category in categories:
        hits = [k for k in _keywords(category) if _matches(normalized, k)]
        if len(hits) > len(best_hits):
            best, best_hits = category, hits

    if best is None:
        best = next((c for c in categories if c["is_fallback"]), categories[-1])
        confidence = 0.3
        reason = "Ключевые слова не найдены — категория по умолчанию."
    else:
        confidence = min(0.5 + 0.1 * len(best_hits), 0.8)
        reason = "Совпали ключевые слова: " + ", ".join(best_hits) + "."

    return Classification(
        category=best,
        confidence=confidence,
        reason=reason,
        draft_reply=best["fallback_reply"].strip() or DEFAULT_REPLY,
        engine="rules",
    )
