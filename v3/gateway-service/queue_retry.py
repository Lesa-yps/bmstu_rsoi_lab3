import requests
import os
from redis import Redis
from rq import Retry, Queue

RENTAL_SERVICE_URL = os.getenv("RENTAL_SERVICE_URL", "http://rental-service:8060")
PAYMENT_SERVICE_URL = os.getenv("PAYMENT_SERVICE_URL", "http://payment-service:8050")

# отметка записи об аренде как отменённой
def _cancel_rental_pending(rental_uid: str, x_user_name: str):
    response = requests.delete(f"{RENTAL_SERVICE_URL}/api/v1/rental/{rental_uid}", headers={"X-User-Name": x_user_name}, timeout=5)
    if response.status_code >= 500:
        raise RuntimeError(f"Rental cancel failed: {response.status_code}")
    if response.status_code >= 400:
        return

# отметка записи об оплате как отменённой
def _cancel_payment_pending(payment_uid: str):
    response = requests.post(f"{PAYMENT_SERVICE_URL}/internal/payments/cancel", params={"payment_uid": payment_uid}, timeout=5)
    if response.status_code >= 500:
        raise RuntimeError(f"Payment cancel failed: {response.status_code}")
    if response.status_code >= 400:
            return


# отмена аренды с повторными попытками в очереди в случае неуспеха
def retry_cancel_rental(rental_uid: str, x_user_name: str):
    queue = Queue(connection=Redis(host="redis", port=6379))
    queue.enqueue(_cancel_rental_pending, rental_uid, x_user_name, retry=Retry(max=100, interval=10))

# отмена оплаты с повторными попытками в очереди в случае неуспеха
def retry_cancel_payment(payment_uid: str):
    queue = Queue(connection=Redis(host="redis", port=6379))
    queue.enqueue(_cancel_payment_pending, payment_uid, retry=Retry(max=100, interval=10))