import pytest

from app import db


@pytest.fixture
def conn(tmp_path):
    connection = db.connect(tmp_path / "test.db")
    db.init_db(connection)
    yield connection
    connection.close()


@pytest.fixture
def categories(conn):
    return db.list_categories(conn)
