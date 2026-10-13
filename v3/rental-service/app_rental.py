import os
from typing import Any

import psycopg2
from fastapi import FastAPI, Header, HTTPException
from psycopg2.extras import RealDictCursor

DB_HOST = os.getenv("DB_HOST", "postgres")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME = os.getenv("DB_NAME", "rentals")
DB_USER = os.getenv("DB_USER", "program")
DB_PASSWORD = os.getenv("DB_PASSWORD", "test")

app = FastAPI(title="Rental Service")


# получение соединения с базой данных
def get_connection():
    return psycopg2.connect(
        host=DB_HOST,
        port=DB_PORT,
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD,
        cursor_factory=RealDictCursor,
    )


# создание таблицы (при необходимости) и заполнение начальными данными
def ensure_schema() -> None:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS rental (
                    id SERIAL PRIMARY KEY,
                    rental_uid uuid UNIQUE NOT NULL,
                    username VARCHAR(80) NOT NULL,
                    payment_uid uuid NOT NULL,
                    car_uid uuid NOT NULL,
                    date_from TIMESTAMP WITH TIME ZONE NOT NULL,
                    date_to TIMESTAMP WITH TIME ZONE NOT NULL,
                    status VARCHAR(20) NOT NULL
                        CHECK (status IN ('IN_PROGRESS', 'FINISHED', 'CANCELED'))
                );
                """
            )
            cur.execute("SELECT COUNT(*) AS total FROM rental")
            if cur.fetchone()["total"] == 0:
                cur.execute(
                    """
                    INSERT INTO rental (rental_uid, username, payment_uid, car_uid, date_from, date_to, status)
                    VALUES
                        ('109b42f3-198d-4c89-9276-a7520a7120ab', 'John Doe', 'd5f0f0b7-8f5d-4a64-b6d7-22ef8c22d0c8', '6f2e0b11-9308-4ef5-a7db-7d0af2dae91d', '2023-10-01 00:00:00+00', '2023-10-05 00:00:00+00', 'IN_PROGRESS'),
                        ('d5f0f0b7-8f5d-4a64-b6d7-22ef8c22d0c8', 'Jane Smith', '6f2e0b11-9308-4ef5-a7db-7d0af2dae91d', '05d1187d-4df2-4c9c-8aec-3b7d042c3f39', '2023-10-10 00:00:00+00', '2023-10-15 00:00:00+00', 'FINISHED');
                    """
                )
            conn.commit()


# запуск функции ensure_schema при старте приложения
@app.on_event("startup")
def startup_event() -> None:
    ensure_schema()


# проверка работоспособности сервиса
@app.get("/manage/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


# получение информации о всех арендах пользователя
@app.get("/api/v1/rental")
def get_user_rentals(
    x_user_name: str = Header(..., alias="X-User-Name")
) -> dict[str, Any]:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    rental_uid AS "rentalUid",
                    username,
                    payment_uid AS "paymentUid",
                    car_uid AS "carUid",
                    date_from AS "dateFrom",
                    date_to AS "dateTo",
                    status
                FROM rental
                WHERE username = %s
                ORDER BY id;
                """,
                (x_user_name,),
            )
            rows = cur.fetchall()
    return {"items": [dict(r) for r in rows]}


# получение информации о конкретной аренде по ее уникальному идентификатору
@app.get("/api/v1/rental/{rental_uid}")
def get_rental_by_uid(
    rental_uid: str,
    x_user_name: str = Header(..., alias="X-User-Name")
) -> dict[str, Any]:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    rental_uid AS "rentalUid",
                    username,
                    payment_uid AS "paymentUid",
                    car_uid AS "carUid",
                    date_from AS "dateFrom",
                    date_to AS "dateTo",
                    status
                FROM rental
                WHERE rental_uid = %s AND username = %s;
                """,
                (rental_uid, x_user_name),
            )
            item = cur.fetchone()

    if item is None:
        raise HTTPException(status_code=404, detail="Rental not found")

    return dict(item)


# забронировать автомобиль
@app.post("/api/v1/rental")
def create_rental(
    rental_data: dict[str, Any],
    x_user_name: str = Header(..., alias="X-User-Name")
) -> dict[str, Any]:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO rental (rental_uid, username, payment_uid, car_uid, date_from, date_to, status)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                RETURNING rental_uid AS "rentalUid", username, payment_uid AS "paymentUid", car_uid AS "carUid", date_from AS "dateFrom", date_to AS "dateTo", status;
                """,
                (
                    rental_data["rentalUid"],
                    x_user_name,
                    rental_data["paymentUid"],
                    rental_data["carUid"],
                    rental_data["dateFrom"],
                    rental_data["dateTo"],
                    rental_data["status"],
                ),
            )
            new_rental = cur.fetchone()
            conn.commit()

    return dict(new_rental)


# завершить аренду автомобиля
@app.post("/api/v1/rental/{rental_uid}/finish")
def finish_rental(
    rental_uid: str,
    x_user_name: str = Header(..., alias="X-User-Name")
) -> dict[str, Any]:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE rental
                SET status = 'FINISHED'
                WHERE rental_uid = %s AND username = %s AND status = 'IN_PROGRESS'
                RETURNING rental_uid AS "rentalUid", username, payment_uid AS "paymentUid", car_uid AS "carUid", date_from AS "dateFrom", date_to AS "dateTo", status;
                """,
                (rental_uid, x_user_name),
            )
            updated_rental = cur.fetchone()
            conn.commit()

    if updated_rental is None:
        raise HTTPException(status_code=404, detail="Rental not found or not in progress")

    return dict(updated_rental)


# отменить аренду автомобиля
@app.delete("/api/v1/rental/{rental_uid}")
def cancel_rental(
    rental_uid: str,
    x_user_name: str = Header(..., alias="X-User-Name")
) -> dict[str, Any]:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE rental
                SET status = 'CANCELED'
                WHERE rental_uid = %s AND username = %s AND status = 'IN_PROGRESS'
                RETURNING rental_uid AS "rentalUid", username, payment_uid AS "paymentUid", car_uid AS "carUid", date_from AS "dateFrom", date_to AS "dateTo", status;
                """,
                (rental_uid, x_user_name),
            )
            updated_rental = cur.fetchone()
            conn.commit()

    if updated_rental is None:
        raise HTTPException(status_code=404, detail="Rental not found or not in progress")

    return dict(updated_rental)


# запуск приложения
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app_rental:app", host="0.0.0.0", port=8060, reload=False)
