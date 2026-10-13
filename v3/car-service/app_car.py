import os
from typing import Any

import psycopg2
from fastapi import FastAPI, HTTPException, Query
from psycopg2.extras import RealDictCursor

DB_HOST = os.getenv("DB_HOST", "postgres")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME = os.getenv("DB_NAME", "cars")
DB_USER = os.getenv("DB_USER", "program")
DB_PASSWORD = os.getenv("DB_PASSWORD", "test")

app = FastAPI(title="Car Service")


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
                CREATE TABLE IF NOT EXISTS cars (
                    id SERIAL PRIMARY KEY,
                    car_uid UUID UNIQUE NOT NULL,
                    brand VARCHAR(80) NOT NULL,
                    model VARCHAR(80) NOT NULL,
                    registration_number VARCHAR(20) NOT NULL,
                    power INT,
                    price INT NOT NULL,
                    type VARCHAR(20) CHECK (type IN ('SEDAN', 'SUV', 'MINIVAN', 'ROADSTER')),
                    availability BOOLEAN NOT NULL
                );
                """
            )
            cur.execute("SELECT COUNT(*) AS total FROM cars")
            if cur.fetchone()["total"] == 0:
                cur.execute(
                    """
                    INSERT INTO cars (car_uid, brand, model, registration_number, power, price, type, availability)
                    VALUES
                        ('109b42f3-198d-4c89-9276-a7520a7120ab', 'Mercedes Benz', 'GLA 250', 'ЛО777Х799', 249, 3500, 'SEDAN', true),
                        ('d5f0f0b7-8f5d-4a64-b6d7-22ef8c22d0c8', 'BMW', 'X5', 'ОЕ123А45', 286, 4200, 'SUV', true),
                        ('6f2e0b11-9308-4ef5-a7db-7d0af2dae91d', 'Kia', 'Carnival', 'НН111Х77', 220, 3100, 'MINIVAN', true),
                        ('05d1187d-4df2-4c9c-8aec-3b7d042c3f39', 'Porsche', '911 Carrera', 'ММ456У12', 385, 5800, 'ROADSTER', true);
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


# получение списка всех доступных для бронирования автомобилей
@app.get("/api/v1/cars")
def get_cars(
    page: int = Query(0, ge=0), # номер страницы (для пагинации)
    size: int = Query(10, ge=1, le=100), # количество элементов на странице (для пагинации)
    showAll: bool = Query(False), # если передан флаг showAll=true, то выводить автомобили в резерве
) -> dict[str, Any]:
    
    offset = page * size
    where_clause = "" if showAll else "WHERE availability = true"

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(f"SELECT COUNT(*) AS total FROM cars {where_clause};")
            total_elements = cur.fetchone()["total"]

            query = f"""
                SELECT
                    car_uid AS \"carUid\",
                    brand,
                    model,
                    registration_number AS \"registrationNumber\",
                    power,
                    type,
                    price,
                    availability AS available
                FROM cars
                {where_clause}
                ORDER BY id
                LIMIT %s OFFSET %s;
            """
            cur.execute(query, (size, offset))
            items = cur.fetchall()

    return {
        "page": page,
        "pageSize": size,
        "totalElements": total_elements,
        "items": [dict(item) for item in items],
    }


# получение информации об автомобиле по его уникальному идентификатору
@app.get("/internal/cars/{car_uid}")
def get_car_by_uid(car_uid: str) -> dict[str, Any]:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    car_uid AS \"carUid\",
                    brand,
                    model,
                    registration_number AS \"registrationNumber\",
                    power,
                    type,
                    price,
                    availability AS available
                FROM cars
                WHERE car_uid = %s;
                """,
                (car_uid,),
            )
            item = cur.fetchone()

    if item is None:
        raise HTTPException(status_code=404, detail="Car not found")

    return dict(item)


# резервирование автомобиля по его уникальному идентификатору
@app.post("/internal/cars/{car_uid}/reserve")
def reserve_car(car_uid: str) -> dict[str, Any]:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE cars
                SET availability = false
                WHERE car_uid = %s AND availability = true
                RETURNING
                    car_uid AS \"carUid\",
                    availability AS available;
                """,
                (car_uid,),
            )
            updated = cur.fetchone()
            conn.commit()

    if updated is None:
        raise HTTPException(status_code=409, detail="Car is not available for reservation")

    return {"carUid": str(updated["carUid"]), "available": updated["available"]}


# освобождение автомобиля по его уникальному идентификатору
@app.post("/internal/cars/{car_uid}/release")
def release_car(car_uid: str) -> dict[str, Any]:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE cars
                SET availability = true
                WHERE car_uid = %s
                RETURNING
                    car_uid AS \"carUid\",
                    availability AS available;
                """,
                (car_uid,),
            )
            updated = cur.fetchone()
            conn.commit()

    if updated is None:
        raise HTTPException(status_code=404, detail="Car not found")

    return {"carUid": str(updated["carUid"]), "available": updated["available"]}


# запуск приложения
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app_car:app", host="0.0.0.0", port=8070, reload=False)
