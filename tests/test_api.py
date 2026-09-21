import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from tests.fakes import FakeLLM, RoutingFakeLLM, llm_answer


def make_client(tmp_path, llm):
    settings = Settings(
        llm_api_key="test-key" if llm else "",
        db_path=str(tmp_path / "api.db"),
        messages_path="messages.txt",
    )
    return TestClient(create_app(settings, llm=llm))


@pytest.fixture
def routing_llm():
    return RoutingFakeLLM({"Wi-Fi": "жалоба", "парковка": "справка"})


@pytest.fixture
def client(tmp_path, routing_llm):
    return make_client(tmp_path, routing_llm)


def _category_id(client, name):
    return next(c["id"] for c in client.get("/api/categories").json() if c["name"] == name)


def test_health_reports_llm_mode_and_model(client):
    body = client.get("/api/health").json()
    assert body["status"] == "ok"
    assert body["llm_configured"] is True
    assert body["model"]


def test_health_without_key_reports_rules_mode(tmp_path):
    body = make_client(tmp_path, None).get("/api/health").json()
    assert body["llm_configured"] is False


def test_classify_returns_and_stores_ticket(client):
    response = client.post("/api/classify", json={"text": "Пропал Wi-Fi в корпусе B."})
    assert response.status_code == 200
    ticket = response.json()
    assert ticket["category"] == "жалоба"
    assert ticket["draft_reply"] == "Ответ для: жалоба"
    assert ticket["engine"] == "llm"
    assert ticket["status"] == "new"
    assert client.get("/api/tickets").json()[0]["id"] == ticket["id"]


def test_classify_without_llm_still_answers_via_rules(tmp_path):
    client = make_client(tmp_path, None)
    ticket = client.post("/api/classify", json={"text": "Где парковка для гостей?"}).json()
    assert ticket["category"] == "справка"
    assert ticket["engine"] == "rules"


@pytest.mark.parametrize("text", ["", "   ", "x" * 4001])
def test_classify_rejects_blank_and_oversized_text(client, text):
    assert client.post("/api/classify", json={"text": text}).status_code == 422


def test_tickets_can_be_filtered_by_category(client):
    client.post("/api/classify", json={"text": "Пропал Wi-Fi"})
    client.post("/api/classify", json={"text": "Где парковка?"})
    spravka = _category_id(client, "справка")
    tickets = client.get("/api/tickets", params={"category_id": spravka}).json()
    assert [t["text"] for t in tickets] == ["Где парковка?"]


def test_operator_saves_final_reply_and_marks_answered(client):
    ticket = client.post("/api/classify", json={"text": "Пропал Wi-Fi"}).json()
    response = client.patch(
        f"/api/tickets/{ticket['id']}", json={"final_reply": "Уже чиним.", "status": "answered"}
    )
    assert response.status_code == 200
    assert response.json()["final_reply"] == "Уже чиним."
    assert response.json()["status"] == "answered"


def test_operator_can_correct_category(client):
    ticket = client.post("/api/classify", json={"text": "Пропал Wi-Fi"}).json()
    other = _category_id(client, "другое")
    updated = client.patch(f"/api/tickets/{ticket['id']}", json={"category_id": other}).json()
    assert updated["category"] == "другое"


def test_patch_ticket_validates_input(client):
    ticket = client.post("/api/classify", json={"text": "Пропал Wi-Fi"}).json()
    assert client.patch(f"/api/tickets/{ticket['id']}", json={"status": "weird"}).status_code == 422
    assert client.patch(f"/api/tickets/{ticket['id']}", json={"category_id": 999}).status_code == 422
    assert client.patch("/api/tickets/999", json={"status": "answered"}).status_code == 404


def test_new_category_is_offered_to_the_llm(tmp_path):
    llm = FakeLLM(llm_answer(category="заявка"))
    client = make_client(tmp_path, llm)
    created = client.post(
        "/api/categories", json={"name": "заявка", "description": "Просьбы записать или выдать."}
    )
    assert created.status_code == 201
    ticket = client.post("/api/classify", json={"text": "Хочу записаться на консультацию"}).json()
    assert "Просьбы записать или выдать." in llm.calls[0]["system"]
    assert ticket["category"] == "заявка"


def test_duplicate_category_name_is_conflict(client):
    assert client.post("/api/categories", json={"name": "ЖАЛОБА"}).status_code == 409


def test_category_can_be_edited(client):
    cat_id = _category_id(client, "жалоба")
    response = client.put(f"/api/categories/{cat_id}", json={"keywords": "сломал, течет"})
    assert response.status_code == 200
    assert response.json()["keywords"] == "сломал, течет"
    assert response.json()["name"] == "жалоба"


def test_category_delete_hides_it_but_fallback_is_protected(client):
    assert client.delete(f"/api/categories/{_category_id(client, 'жалоба')}").status_code == 204
    assert "жалоба" not in [c["name"] for c in client.get("/api/categories").json()]
    assert client.delete(f"/api/categories/{_category_id(client, 'другое')}").status_code == 409
    assert client.delete("/api/categories/999").status_code == 404


def test_batch_classifies_in_input_order_and_stores_all(client):
    texts = ["Где парковка?", "Пропал Wi-Fi", "Хочу записаться"]
    response = client.post("/api/batch", json={"texts": texts})
    assert response.status_code == 200
    assert [t["category"] for t in response.json()] == ["справка", "жалоба", "другое"]
    assert [t["text"] for t in response.json()] == texts
    assert len(client.get("/api/tickets").json()) == 3


def test_batch_rejects_empty_list(client):
    assert client.post("/api/batch", json={"texts": []}).status_code == 422


def test_sample_messages_come_from_messages_file(client):
    messages = client.get("/api/sample-messages").json()
    assert len(messages) == 5
    assert messages[4] == "Где парковка для гостей?"


def test_stats_count_tickets_per_category(client):
    client.post("/api/classify", json={"text": "Пропал Wi-Fi"})
    stats = client.get("/api/stats").json()
    assert stats["total"] == 1
    assert {c["name"]: c["count"] for c in stats["by_category"]}["жалоба"] == 1


def test_index_page_is_served(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
