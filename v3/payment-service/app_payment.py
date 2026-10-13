import os
from typing import Any

import psycopg2
from fastapi import FastAPI, HTTPException
from psycopg2.extras import RealDictCursor

DB_HOST = os.getenv("DB_HOST", "postgres")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME = os.getenv("DB_NAME", "payments")
DB_USER = os.getenv("DB_USER", "program")
DB_PASSWORD = os.getenv("DB_PASSWORD", "test")

app = FastAPI(title="Payment Service")


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
                CREATE TABLE IF NOT EXISTS payment
                (
                    id SERIAL PRIMARY KEY,
                    payment_uid uuid NOT NULL,
                    status VARCHAR(20) NOT NULL
                        CHECK (status IN ('PAID', 'CANCELED')),
                    price INT NOT NULL
               );
                """
            )
            cur.execute("SELECT COUNT(*) AS total FROM payment")
            if cur.fetchone()["total"] == 0:
                cur.execute(
                    """
                    INSERT INTO payment (payment_uid, status, price)
                    VALUES
                        ('109b42f3-198d-4c89-9276-a7520a7120ab', 'PAID', 3500),
                        ('d5f0f0b7-8f5d-4a64-b6d7-22ef8c22d0c8', 'CANCELED', 4200),
                        ('6f2e0b11-9308-4ef5-a7db-7d0af2dae91d', 'PAID', 3100),
                        ('05d1187d-4df2-4c9c-8aec-3b7d042c3f39', 'CANCELED', 5800);
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


# создание платежа
@app.post("/internal/payments")
def create_payment(payment_uid: str, price: int) -> dict[str, Any]:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO payment (payment_uid, status, price)
                VALUES (%s, 'PAID', %s)
                RETURNING
                    payment_uid AS \"paymentUid\",
                    status,
                    price;
                """,
                (payment_uid, price),
            )
            new_payment = cur.fetchone()
            conn.commit()

    return dict(new_payment)


# отмена платежа
@app.post("/internal/payments/cancel")
def cancel_payment(payment_uid: str) -> dict[str, Any]:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE payment
                SET status = 'CANCELED'
                WHERE payment_uid = %s AND status = 'PAID'
                RETURNING
                    payment_uid AS \"paymentUid\",
                    status,
                    price;
                """,
                (payment_uid,),
            )
            updated_payment = cur.fetchone()
            conn.commit()

    if updated_payment is None:
        raise HTTPException(status_code=404, detail="Payment not found or already canceled")

    return dict(updated_payment)


# получение информации о платеже по его уникальному идентификатору
@app.get("/internal/payments/{payment_uid}")
def get_payment_by_uid(payment_uid: str) -> dict[str, Any]:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    payment_uid AS \"paymentUid\",
                    status,
                    price
                FROM payment
                WHERE payment_uid = %s;
                """,
                (payment_uid,),
            )
            item = cur.fetchone()

    if item is None:
        raise HTTPException(status_code=404, detail="Payment not found")

    return dict(item)


# запуск приложения
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app_payment:app", host="0.0.0.0", port=8050, reload=False)
