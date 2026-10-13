# unit тесты для rental-service

import pytest
from unittest.mock import MagicMock
from fastapi.testclient import TestClient

import app_payment as app_module
from app_payment import app


# фикстура, которая мокает get_connection и возвращает мок-курсор
@pytest.fixture
def mock_db(monkeypatch):
    mock_cursor = MagicMock()
    mock_conn = MagicMock()

    # get_connection() as conn: -> возвращает mock_conn
    mock_conn.__enter__.return_value = mock_conn
    mock_conn.__exit__.return_value = False

    # with conn.cursor() as cur: -> возвращает mock_cursor
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
    mock_conn.cursor.return_value.__exit__.return_value = False

    # заглушается get_connection в модуле app
    monkeypatch.setattr(app_module, "get_connection", lambda: mock_conn)

    # не запускается ensure_schema при старте
    monkeypatch.setattr(app_module, "ensure_schema", lambda: None)

    return TestClient(app), mock_cursor # TestClient без реального запуска БД


# тест на создание платежа
def test_create_payment(mock_db):
    test_client, mock_cursor = mock_db

    return_value = {
        "paymentUid": "109b42f3-198d-4c89-9276-a7520a7120ab",
        "status": "PAID",
        "price": 3500,
    }

    mock_cursor.fetchone.return_value = return_value

    response = test_client.post(
        "/internal/payments",
        params={"payment_uid": "109b42f3-198d-4c89-9276-a7520a7120ab", "price": 3500}
    )

    assert response.status_code == 200
    assert response.json() == return_value


# тест на отмену платежа
def test_cancel_payment(mock_db):
    test_client, mock_cursor = mock_db

    return_value = {
        "paymentUid": "109b42f3-198d-4c89-9276-a7520a7120ab",
        "status": "CANCELED",
        "price": 3500,
    }

    mock_cursor.fetchone.return_value = return_value

    response = test_client.post(
        "/internal/payments/cancel",
        params={"payment_uid": "109b42f3-198d-4c89-9276-a7520a7120ab"}
    )

    assert response.status_code == 200
    assert response.json() == return_value