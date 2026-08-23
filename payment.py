import os
import logging
import httpx

logger = logging.getLogger(__name__)

ZARINPAL_MERCHANT_ID = os.getenv("ZARINPAL_MERCHANT_ID", "").strip()
PAYMENT_CALLBACK_URL = os.getenv("PAYMENT_CALLBACK_URL", "").strip()

ZARINPAL_REQUEST_URL = (
    "https://payment.zarinpal.com/pg/v4/payment/request.json"
)

ZARINPAL_VERIFY_URL = (
    "https://payment.zarinpal.com/pg/v4/payment/verify.json"
)

ZARINPAL_STARTPAY_URL = (
    "https://www.zarinpal.com/pg/StartPay/"
)


class PaymentError(Exception):
    pass


def _check_config():
    if not ZARINPAL_MERCHANT_ID:
        raise PaymentError("ZARINPAL_MERCHANT_ID is not configured")

    if not PAYMENT_CALLBACK_URL:
        raise PaymentError("PAYMENT_CALLBACK_URL is not configured")


async def create_payment(
    amount_toman: int,
    description: str,
    callback_url: str | None = None,
):
    """
    ایجاد تراکنش زرین‌پال.

    amount_toman:
        مبلغ به تومان

    زرین‌پال:
        مبلغ را به ریال دریافت می‌کند.
    """

    _check_config()

    amount_toman = int(amount_toman)

    if amount_toman <= 0:
        raise PaymentError("INVALID_AMOUNT")

    amount_rial = amount_toman * 10

    callback = callback_url or PAYMENT_CALLBACK_URL

    payload = {
        "merchant_id": ZARINPAL_MERCHANT_ID,
        "amount": amount_rial,
        "callback_url": callback,
        "description": description[:500],
    }

    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

    try:
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.post(
                ZARINPAL_REQUEST_URL,
                json=payload,
                headers=headers,
            )

        response.raise_for_status()
        data = response.json()

    except httpx.HTTPError as exc:
        logger.exception("Zarinpal request HTTP error")
        raise PaymentError("PAYMENT_GATEWAY_ERROR") from exc

    except Exception as exc:
        logger.exception("Zarinpal request failed")
        raise PaymentError("PAYMENT_REQUEST_FAILED") from exc

    data_block = data.get("data") or {}

    code = data_block.get("code")

    if code != 100:
        errors = data.get("errors") or {}

        logger.error(
            "Zarinpal request rejected: code=%s errors=%s",
            code,
            errors,
        )

        raise PaymentError(
            f"PAYMENT_REQUEST_REJECTED:{code}"
        )

    authority = data_block.get("authority")

    if not authority:
        raise PaymentError("AUTHORITY_NOT_RECEIVED")

    return {
        "authority": authority,
        "payment_url": f"{ZARINPAL_STARTPAY_URL}{authority}",
        "amount_toman": amount_toman,
        "amount_rial": amount_rial,
    }


async def verify_payment(
    amount_toman: int,
    authority: str,
):
    """
    Verify تراکنش زرین‌پال.

    خروجی:
        {
            "success": True,
            "ref_id": ...,
            "code": 100
        }

    در صورت پرداخت ناموفق:
        success=False
    """

    _check_config()

    amount_toman = int(amount_toman)

    if amount_toman <= 0:
        raise PaymentError("INVALID_AMOUNT")

    if not authority:
        raise PaymentError("INVALID_AUTHORITY")

    amount_rial = amount_toman * 10

    payload = {
        "merchant_id": ZARINPAL_MERCHANT_ID,
        "amount": amount_rial,
        "authority": authority,
    }

    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

    try:
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.post(
                ZARINPAL_VERIFY_URL,
                json=payload,
                headers=headers,
            )

        response.raise_for_status()
        data = response.json()

    except httpx.HTTPError as exc:
        logger.exception("Zarinpal verify HTTP error")
        raise PaymentError("VERIFY_GATEWAY_ERROR") from exc

    except Exception as exc:
        logger.exception("Zarinpal verify failed")
        raise PaymentError("VERIFY_FAILED") from exc

    data_block = data.get("data") or {}

    code = data_block.get("code")
    ref_id = data_block.get("ref_id")

    if code == 100:
        if not ref_id:
            raise PaymentError("REF_ID_NOT_RECEIVED")

        return {
            "success": True,
            "code": code,
            "ref_id": ref_id,
        }

    if code == 101:
        return {
            "success": False,
            "already_verified": True,
            "code": code,
            "ref_id": ref_id,
        }

    errors = data.get("errors") or {}

    logger.warning(
        "Zarinpal verification failed: code=%s errors=%s",
        code,
        errors,
    )

    return {
        "success": False,
        "already_verified": False,
        "code": code,
        "ref_id": ref_id,
    }
