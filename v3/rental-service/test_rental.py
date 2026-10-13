# unit тесты для car-service

import json

import pytest
from unittest.mock import MagicMock
from fastapi.testclient import TestClient

import app_rental as app_module
from app_rental import app


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


# тест на создание аренды автомобиля (забронирование)
def test_create_rental(mock_db):
    test_client, mock_cursor = mock_db

    request_body = {
        "rentalUid": '109b42f3-198d-4c89-9276-a7520a7120ab',
        "paymentUid": 'd5f0f0b7-8f5d-4a64-b6d7-22ef8c22d0c8',
        "carUid": '6f2e0b11-9308-4ef5-a7db-7d0af2dae91d',
        "dateFrom": '2023-10-01 00:00:00+00',
        "dateTo": '2023-10-05 00:00:00+00',
        "status": 'IN_PROGRESS'
    }

    return_value = request_body.copy()
    return_value["username"] = "John Doe"

    mock_cursor.fetchone.return_value = return_value

    response = test_client.post(
        "/api/v1/rental",
        json=request_body,                      # тело запроса
        headers={"X-User-Name": "John Doe"},    # заголовок
    )

    assert response.status_code == 200
    assert response.json() == return_value


# тест на завершение аренды автомобиля
def test_finish_rental(mock_db):
    test_client, mock_cursor = mock_db

    return_value = {
        "rentalUid": '109b42f3-198d-4c89-9276-a7520a7120ab',
        'username': 'John Doe',
        "paymentUid": 'd5f0f0b7-8f5d-4a64-b6d7-22ef8c22d0c8',
        "carUid": '6f2e0b11-9308-4ef5-a7db-7d0af2dae91d',
        "dateFrom": '2023-10-01 00:00:00+00',
        "dateTo": '2023-10-05 00:00:00+00',
        "status": 'FINISHED'
    }

    mock_cursor.fetchone.return_value = return_value

    response = test_client.post(
        "/api/v1/rental/{rental_uid}/finish",
        params={"rental_uid": "109b42f3-198d-4c89-9276-a7520a7120ab"},
        headers={"X-User-Name": "John Doe"},    # заголовок
    )

    assert response.status_code == 200
    assert response.json() == return_value


# тест на отмену аренды автомобиля
def test_cancel_rental(mock_db):
    test_client, mock_cursor = mock_db

    return_value = {
        "rentalUid": '109b42f3-198d-4c89-9276-a7520a7120ab',
        'username': 'John Doe',
        "paymentUid": 'd5f0f0b7-8f5d-4a64-b6d7-22ef8c22d0c8',
        "carUid": '6f2e0b11-9308-4ef5-a7db-7d0af2dae91d',
        "dateFrom": '2023-10-01 00:00:00+00',
        "dateTo": '2023-10-05 00:00:00+00',
        "status": 'CANCELLED'
    }

    mock_cursor.fetchone.return_value = return_value

    response = test_client.delete(
        "/api/v1/rental/{rental_uid}",
        params={"rental_uid": "109b42f3-198d-4c89-9276-a7520a7120ab"},
        headers={"X-User-Name": "John Doe"},    # заголовок
    )

    assert response.status_code == 200
    assert response.json() == return_value