from dataclasses import dataclass


@dataclass
class Classification:
    """Итог разбора одного обращения, независимо от того, кто его сделал."""

    category: dict
    confidence: float
    reason: str
    draft_reply: str
    engine: str  # "llm" или "rules"
    model: str | None = None
    latency_ms: int = 0
