import pytest

from app import db


def test_init_seeds_three_default_categories(conn):
    names = [c["name"] for c in db.list_categories(conn)]
    assert names == ["справка", "жалоба", "другое"]


def test_exactly_one_fallback_category_and_it_is_drugoe(conn):
    fallbacks = [c for c in db.list_categories(conn) if c["is_fallback"]]
    assert [c["name"] for c in fallbacks] == ["другое"]


def test_init_is_idempotent_and_keeps_user_edits(conn):
    first = db.list_categories(conn)[0]
    db.update_category(conn, first["id"], description="моё описание")
    db.init_db(conn)
    cats = db.list_categories(conn)
    assert len(cats) == 3
    assert cats[0]["description"] == "моё описание"


def test_create_category_rejects_duplicate_name(conn):
    with pytest.raises(db.DuplicateCategory):
        db.create_category(conn, name="Жалоба", description="x")


def test_deactivated_category_disappears_from_active_list(conn):
    cat = db.create_category(conn, name="заявка", description="просьбы")
    db.deactivate_category(conn, cat["id"])
    assert "заявка" not in [c["name"] for c in db.list_categories(conn)]


def test_fallback_category_cannot_be_deactivated(conn):
    fallback = next(c for c in db.list_categories(conn) if c["is_fallback"])
    with pytest.raises(db.FallbackCategoryProtected):
        db.deactivate_category(conn, fallback["id"])


def _ticket(conn, text, category_name, engine="llm"):
    cat = next(c for c in db.list_categories(conn) if c["name"] == category_name)
    return db.insert_ticket(
        conn,
        text=text,
        source="test",
        category_id=cat["id"],
        confidence=0.9,
        reason="потому что",
        draft_reply="Здравствуйте!",
        engine=engine,
        model="fake",
        latency_ms=12,
    )


def test_inserted_ticket_is_returned_with_category_name_and_new_status(conn):
    ticket = _ticket(conn, "Где парковка?", "справка")
    assert ticket["category"] == "справка"
    assert ticket["status"] == "new"
    assert ticket["final_reply"] is None


def test_list_tickets_newest_first_and_filtered_by_category(conn):
    _ticket(conn, "первое", "справка")
    _ticket(conn, "второе", "жалоба")
    _ticket(conn, "третье", "справка")
    assert [t["text"] for t in db.list_tickets(conn)] == ["третье", "второе", "первое"]
    spravka_id = db.list_categories(conn)[0]["id"]
    filtered = db.list_tickets(conn, category_id=spravka_id)
    assert [t["text"] for t in filtered] == ["третье", "первое"]


def test_update_ticket_saves_final_reply_and_status(conn):
    ticket = _ticket(conn, "Пропал Wi-Fi", "жалоба")
    updated = db.update_ticket(conn, ticket["id"], final_reply="Чиним", status="answered")
    assert updated["final_reply"] == "Чиним"
    assert updated["status"] == "answered"


def test_update_missing_ticket_returns_none(conn):
    assert db.update_ticket(conn, 999, status="answered") is None


def test_stats_counts_tickets_per_category_including_empty_ones(conn):
    _ticket(conn, "a", "справка")
    _ticket(conn, "b", "справка", engine="rules")
    stats = db.stats(conn)
    assert stats["total"] == 2
    by_name = {c["name"]: c["count"] for c in stats["by_category"]}
    assert by_name == {"справка": 2, "жалоба": 0, "другое": 0}
    assert stats["by_engine"] == {"llm": 1, "rules": 1}
