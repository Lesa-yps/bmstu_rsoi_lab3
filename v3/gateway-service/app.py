import os
from datetime import date
from typing import Any, Literal
from uuid import UUID, uuid4

import requests
from fastapi import FastAPI, Header, HTTPException, Query, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.openapi.utils import get_openapi
from fastapi.responses import JSONResponse
from pydantic import BaseModel

app = FastAPI(
    title="Car Rental System",
    version="1.0",
    openapi_version="3.0.1",
    servers=[{"url": "http://localhost:8080"}],
)
CAR_SERVICE_URL = os.getenv("CAR_SERVICE_URL", "http://car-service:8070")
RENTAL_SERVICE_URL = os.getenv("RENTAL_SERVICE_URL", "http://rental-service:8060")
PAYMENT_SERVICE_URL = os.getenv("PAYMENT_SERVICE_URL", "http://payment-service:8050")


class CreateRentalRequest(BaseModel):
    carUid: UUID
    dateFrom: date
    dateTo: date


class CarResponse(BaseModel):
    carUid: UUID
    brand: str
    model: str
    registrationNumber: str
    power: int | None = None
    type: str
    price: int
    available: bool


class PaginationResponse(BaseModel):
    page: int
    pageSize: int
    totalElements: int
    items: list[CarResponse]


class CarInfo(BaseModel):
    carUid: UUID
    brand: str
    model: str
    registrationNumber: str


class PaymentInfo(BaseModel):
    paymentUid: UUID
    status: Literal["PAID", "CANCELED", "REVERSED"]
    price: int


class RentalResponse(BaseModel):
    rentalUid: UUID
    status: Literal["NEW", "IN_PROGRESS", "FINISHED", "CANCELED"]
    dateFrom: date
    dateTo: date
    car: CarInfo
    payment: PaymentInfo


class CreateRentalResponse(BaseModel):
    rentalUid: UUID
    status: Literal["IN_PROGRESS", "FINISHED", "CANCELED"]
    carUid: UUID
    dateFrom: date
    dateTo: date
    payment: PaymentInfo


class ErrorResponse(BaseModel):
    message: str


class ErrorDescription(BaseModel):
    field: str
    error: str


class ValidationErrorResponse(BaseModel):
    message: str
    errors: list[ErrorDescription]


# ОШИБКИ
@app.exception_handler(RequestValidationError)
async def handle_validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
    errors = [
        {
            "field": ".".join(str(part) for part in error["loc"][1:]),
            "error": error["msg"],
        }
        for error in exc.errors()
    ]
    return JSONResponse(
        status_code=400,
        content={"message": "Validation error", "errors": errors},
    )


@app.exception_handler(HTTPException)
async def handle_http_error(request: Request, exc: HTTPException) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content={"message": exc.detail})


def call_service(method: str, url: str, **kwargs: Any) -> requests.Response:
    try:
        response = requests.request(method, url, timeout=5, **kwargs)
    except requests.RequestException as exc:
        raise HTTPException(status_code=502, detail="A dependent service is unavailable") from exc

    if response.status_code >= 400:
        try:
            body = response.json()
            detail = body.get("message", body.get("detail", response.text))
        except ValueError:
            detail = response.text or "Dependent service request failed"
        raise HTTPException(status_code=response.status_code, detail=detail)

    return response


def build_rental_response(rental: dict[str, Any]) -> dict[str, Any]:
    car_uid = rental["carUid"]
    payment_uid = rental["paymentUid"]
    car = call_service("GET", f"{CAR_SERVICE_URL}/internal/cars/{car_uid}").json()
    payment = call_service(
        "GET", f"{PAYMENT_SERVICE_URL}/internal/payments/{payment_uid}"
    ).json()
    return {
        "rentalUid": str(rental["rentalUid"]),
        "status": rental["status"],
        "dateFrom": str(rental["dateFrom"]).split("T", 1)[0],
        "dateTo": str(rental["dateTo"]).split("T", 1)[0],
        "car": {
            "carUid": str(car["carUid"]),
            "brand": car["brand"],
            "model": car["model"],
            "registrationNumber": car["registrationNumber"],
        },
        "payment": {
            "paymentUid": str(payment["paymentUid"]),
            "status": payment["status"],
            "price": payment["price"],
        },
    }


# проверка работоспособности сервиса
@app.get("/manage/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


# получение списка всех доступных для бронирования автомобилей
@app.get(
    "/api/v1/cars",
    response_model=PaginationResponse,
    summary="Получить список всех доступных для бронирования автомобилей",
    tags=["Gateway API"],
)
def get_cars(
    page: int = Query(0, ge=0), # номер страницы (для пагинации)
    size: int = Query(10, ge=1, le=100), # количество элементов на странице (для пагинации)
    showAll: bool = Query(False), # если передан флаг showAll=true, то выводить автомобили в резерве
) -> dict[str, Any]:
    response = call_service(
        "GET",
        f"{CAR_SERVICE_URL}/api/v1/cars",
        params={"page": max(page - 1, 0), "size": size, "showAll": showAll},
    ).json()
    response["page"] = page
    return response


# получение информации о всех арендах пользователя
@app.get(
    "/api/v1/rental",
    response_model=list[RentalResponse],
    summary="Получить информацию о всех арендах пользователя",
    tags=["Gateway API"],
)
def get_user_rentals(
    x_user_name: str = Header(..., alias="X-User-Name"),
) -> list[dict[str, Any]]:
    response = call_service(
        "GET",
        f"{RENTAL_SERVICE_URL}/api/v1/rental",
        headers={"X-User-Name": x_user_name},
    ).json()
    return [build_rental_response(rental) for rental in response["items"]]


# забронировать автомобиль
@app.post(
    "/api/v1/rental",
    response_model=CreateRentalResponse,
    responses={400: {"model": ValidationErrorResponse, "description": "Ошибка валидации данных"}},
    summary="Забронировать автомобиль",
    tags=["Gateway API"],
)
def create_rental(
    rental_data: CreateRentalRequest,
    x_user_name: str = Header(..., alias="X-User-Name"),
) -> dict[str, Any] | JSONResponse:
    if rental_data.dateTo <= rental_data.dateFrom:
        return JSONResponse(
            status_code=400,
            content={
                "message": "Validation error",
                "errors": [{"field": "dateTo", "error": "Must be later than dateFrom"}],
            },
        )

    # получение машины по carUid
    car_uid = str(rental_data.carUid)
    try:
        try:
            car = call_service("GET", f"{CAR_SERVICE_URL}/internal/cars/{car_uid}").json()
        except HTTPException as exc:
            if exc.status_code == 404:
                return JSONResponse(
                    status_code=400,
                    content={
                        "message": "Validation error",
                        "errors": [{"field": "carUid", "error": "Car not found"}],
                    },
                )
            raise

        # попытка зарезервировать автомобиль
        try:
            call_service("POST", f"{CAR_SERVICE_URL}/internal/cars/{car_uid}/reserve")
        except HTTPException as exc:
            if exc.status_code in (404, 409):
                return JSONResponse(
                    status_code=400,
                    content={
                        "message": "Validation error",
                        "errors": [{"field": "carUid", "error": str(exc.detail)}],
                    },
                )
            raise

        rental_uid = uuid4()
        payment_uid = uuid4()
        rental_days = (rental_data.dateTo - rental_data.dateFrom).days
        price = car["price"] * rental_days

        # запись в сервис оплаты
        payment_response = call_service(
            "POST",
            f"{PAYMENT_SERVICE_URL}/internal/payments",
            params={"payment_uid": str(payment_uid), "price": price},
        )
        payment = payment_response.json()

        # запись в сервис аренды
        rental_response = call_service(
            "POST",
            f"{RENTAL_SERVICE_URL}/api/v1/rental",
            headers={"X-User-Name": x_user_name},
            json={
                "rentalUid": str(rental_uid),
                "paymentUid": str(payment_uid),
                "carUid": car_uid,
                "dateFrom": rental_data.dateFrom.isoformat(),
                "dateTo": rental_data.dateTo.isoformat(),
                "status": "IN_PROGRESS",
            },
        )
        rental = rental_response.json()
    except HTTPException:
        raise
    except requests.RequestException as exc:
        raise HTTPException(status_code=502, detail="A dependent service is unavailable") from exc

    return {
        "rentalUid": str(rental["rentalUid"]),
        "status": rental["status"],
        "carUid": str(rental["carUid"]),
        "dateFrom": rental_data.dateFrom.isoformat(),
        "dateTo": rental_data.dateTo.isoformat(),
        "payment": payment,
    }


# информация о конкретной аренде пользователя по rentalUid
@app.get(
    "/api/v1/rental/{rentalUid}",
    response_model=RentalResponse,
    responses={404: {"model": ErrorResponse, "description": "Аренда не найдена"}},
    summary="Информация по конкретной аренде пользователя",
    tags=["Gateway API"],
)
def get_rental_by_uid(
    rentalUid: UUID,
    x_user_name: str = Header(..., alias="X-User-Name"),
) -> dict[str, Any]:
    rental_response = call_service(
        "GET",
        f"{RENTAL_SERVICE_URL}/api/v1/rental/{rentalUid}",
        headers={"X-User-Name": x_user_name},
    )
    return build_rental_response(rental_response.json())


# отмена аренды автомобиля по rentalUid
@app.delete(
    "/api/v1/rental/{rentalUid}",
    status_code=204,
    response_class=Response,
    responses={
        204: {"description": "Аренда успешно отменена"},
        404: {"model": ErrorResponse, "description": "Аренда не найдена"},
    },
    summary="Отмена аренды автомобиля",
    tags=["Gateway API"],
)
def cancel_rental(
    rentalUid: UUID,
    x_user_name: str = Header(..., alias="X-User-Name"),
) -> Response:
    rental = call_service(
        "GET",
        f"{RENTAL_SERVICE_URL}/api/v1/rental/{rentalUid}",
        headers={"X-User-Name": x_user_name},
    ).json()
    call_service(
        "POST",
        f"{PAYMENT_SERVICE_URL}/internal/payments/cancel",
        params={"payment_uid": rental["paymentUid"]},
    )
    call_service("POST", f"{CAR_SERVICE_URL}/internal/cars/{rental['carUid']}/release")
    call_service(
        "DELETE",
        f"{RENTAL_SERVICE_URL}/api/v1/rental/{rentalUid}",
        headers={"X-User-Name": x_user_name},
    )
    return Response(status_code=204)


# завершение аренды автомобиля по rentalUid
@app.post(
    "/api/v1/rental/{rentalUid}/finish",
    status_code=204,
    response_class=Response,
    responses={
        204: {"description": "Аренда успешно завершена"},
        404: {"model": ErrorResponse, "description": "Аренда не найдена"},
    },
    summary="Завершение аренды автомобиля",
    tags=["Gateway API"],
)
def finish_rental(
    rentalUid: UUID,
    x_user_name: str = Header(..., alias="X-User-Name"),
) -> Response:
    rental = call_service(
        "GET",
        f"{RENTAL_SERVICE_URL}/api/v1/rental/{rentalUid}",
        headers={"X-User-Name": x_user_name},
    ).json()
    call_service("POST", f"{CAR_SERVICE_URL}/internal/cars/{rental['carUid']}/release")
    call_service(
        "POST",
        f"{RENTAL_SERVICE_URL}/api/v1/rental/{rentalUid}/finish",
        headers={"X-User-Name": x_user_name},
    )
    return Response(status_code=204)


def custom_openapi() -> dict[str, Any]:
    if app.openapi_schema:
        return app.openapi_schema

    schema = get_openapi(
        title=app.title,
        version=app.version,
        openapi_version=app.openapi_version,
        routes=app.routes,
        servers=app.servers,
    )
    schema["openapi"] = "3.0.1"
    power_schema = schema["components"]["schemas"]["CarResponse"]["properties"]["power"]
    if "anyOf" in power_schema:
        power_schema.clear()
        power_schema.update({"type": "integer", "nullable": True, "title": "Power"})
    for path_item in schema["paths"].values():
        for operation in path_item.values():
            if isinstance(operation, dict):
                operation.get("responses", {}).pop("422", None)

    app.openapi_schema = schema
    return schema


app.openapi = custom_openapi


# запуск приложения
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=8080, reload=False)
