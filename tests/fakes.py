import json


def llm_answer(**overrides) -> str:
    data = {
        "category": "жалоба",
        "confidence": 0.92,
        "reason": "Сообщение о сбое.",
        "draft_reply": "Здравствуйте! Приносим извинения, передали заявку в ИТ-службу.",
    }
    data.update(overrides)
    return json.dumps(data, ensure_ascii=False)


class FakeLLM:
    """Отдаёт заранее заданные ответы по очереди; исключение в очереди — бросает."""

    model = "fake-model"

    def __init__(self, *answers):
        self.answers = list(answers)
        self.calls = []

    def complete(self, system: str, user: str) -> str:
        self.calls.append({"system": system, "user": user})
        answer = self.answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return answer


class RoutingFakeLLM:
    """Отвечает по содержимому обращения — порядок вызовов не важен (для параллельных)."""

    model = "fake-model"

    def __init__(self, routes: dict[str, str], default: str = "другое"):
        self.routes = routes
        self.default = default
        self.calls = []

    def complete(self, system: str, user: str) -> str:
        self.calls.append({"system": system, "user": user})
        category = next((cat for needle, cat in self.routes.items() if needle in user), self.default)
        return llm_answer(category=category, draft_reply=f"Ответ для: {category}")
