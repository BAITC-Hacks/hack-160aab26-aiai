"""HTTP API и веб-интерфейс сервиса разбора обращений."""

from collections.abc import Iterator
from pathlib import Path
from typing import Annotated, Literal

from fastapi import Depends, FastAPI, HTTPException, Response
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, StringConstraints

from app import db
from app.classifier import LLM, classify, classify_many
from app.config import Settings, load_env_file
from app.llm import LLMClient
from app.messages import parse_messages

STATIC_DIR = Path(__file__).parent / "static"
_FROM_SETTINGS = object()

MessageText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=4000)]
CategoryName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=60)]
LongText = Annotated[str, StringConstraints(max_length=2000)]


class ClassifyIn(BaseModel):
    text: MessageText
    source: Annotated[str, StringConstraints(max_length=30)] = "web"


class BatchIn(BaseModel):
    texts: list[MessageText] = Field(min_length=1, max_length=50)


class CategoryIn(BaseModel):
    name: CategoryName
    description: LongText = ""
    reply_hint: LongText = ""
    keywords: LongText = ""
    fallback_reply: LongText = ""


class CategoryPatch(BaseModel):
    name: CategoryName | None = None
    description: LongText | None = None
    reply_hint: LongText | None = None
    keywords: LongText | None = None
    fallback_reply: LongText | None = None


class TicketPatch(BaseModel):
    final_reply: Annotated[str, StringConstraints(max_length=8000)] | None = None
    status: Literal["new", "answered"] | None = None
    category_id: int | None = None


def create_app(settings: Settings | None = None, llm: LLM | None = _FROM_SETTINGS) -> FastAPI:
    settings = settings or Settings.from_env()
    if llm is _FROM_SETTINGS:
        llm = LLMClient(settings) if settings.llm_configured else None

    conn = db.connect(settings.db_path)
    db.init_db(conn)
    conn.close()

    app = FastAPI(title="Классификатор обращений", version="1.0.0")

    def get_conn() -> Iterator:
        conn = db.connect(settings.db_path)
        try:
            yield conn
        finally:
            conn.close()

    @app.get("/api/health")
    def health(conn=Depends(get_conn)):
        conn.execute("SELECT 1")
        return {
            "status": "ok",
            "llm_configured": llm is not None,
            "model": settings.llm_model if llm is not None else None,
            "org_name": settings.org_name,
        }

    @app.post("/api/classify")
    def classify_one(body: ClassifyIn, conn=Depends(get_conn)):
        result = classify(body.text, db.list_categories(conn), llm, settings.org_name)
        return db.save_classification(conn, body.text, body.source, result)

    @app.post("/api/batch")
    def classify_batch(body: BatchIn, conn=Depends(get_conn)):
        results = classify_many(body.texts, db.list_categories(conn), llm, settings.org_name)
        return [
            db.save_classification(conn, text, "batch", result)
            for text, result in zip(body.texts, results)
        ]

    @app.get("/api/sample-messages")
    def sample_messages():
        path = Path(settings.messages_path)
        return parse_messages(path.read_text(encoding="utf-8")) if path.is_file() else []

    @app.get("/api/tickets")
    def tickets(
        category_id: int | None = None,
        status: Literal["new", "answered"] | None = None,
        limit: Annotated[int, Field(ge=1, le=500)] = 200,
        conn=Depends(get_conn),
    ):
        return db.list_tickets(conn, category_id=category_id, status=status, limit=limit)

    @app.patch("/api/tickets/{ticket_id}")
    def patch_ticket(ticket_id: int, body: TicketPatch, conn=Depends(get_conn)):
        if body.category_id is not None and db.get_category(conn, body.category_id) is None:
            raise HTTPException(422, "Такой категории нет")
        ticket = db.update_ticket(conn, ticket_id, **body.model_dump())
        if ticket is None:
            raise HTTPException(404, "Обращение не найдено")
        return ticket

    @app.get("/api/categories")
    def categories(conn=Depends(get_conn)):
        return db.list_categories(conn)

    @app.post("/api/categories", status_code=201)
    def create_category(body: CategoryIn, conn=Depends(get_conn)):
        try:
            return db.create_category(conn, **body.model_dump())
        except db.DuplicateCategory as exc:
            raise HTTPException(409, str(exc)) from exc

    @app.put("/api/categories/{category_id}")
    def update_category(category_id: int, body: CategoryPatch, conn=Depends(get_conn)):
        try:
            category = db.update_category(conn, category_id, **body.model_dump())
        except db.DuplicateCategory as exc:
            raise HTTPException(409, str(exc)) from exc
        if category is None:
            raise HTTPException(404, "Категория не найдена")
        return category

    @app.delete("/api/categories/{category_id}", status_code=204)
    def delete_category(category_id: int, conn=Depends(get_conn)):
        try:
            found = db.deactivate_category(conn, category_id)
        except db.FallbackCategoryProtected as exc:
            raise HTTPException(409, str(exc)) from exc
        if not found:
            raise HTTPException(404, "Категория не найдена")
        return Response(status_code=204)

    @app.get("/api/stats")
    def stats(conn=Depends(get_conn)):
        return db.stats(conn)

    @app.get("/", include_in_schema=False)
    def index():
        return FileResponse(STATIC_DIR / "index.html", media_type="text/html")

    return app


def app_from_env() -> FastAPI:
    """Фабрика для uvicorn: `uvicorn app.main:app_from_env --factory`."""
    load_env_file(".env")
    return create_app()
