from decimal import Decimal, InvalidOperation

import httpx

from .config import settings


class MonolithUnavailableError(RuntimeError):
    pass


class MonolithDataError(RuntimeError):
    pass


async def fetch_match_ticketing_info(match_id: int) -> dict | None:
    base_url = settings.MONOLITH_API_BASE_URL.rstrip("/")
    url = f"{base_url}/api/matches/{match_id}/ticketing/"

    try:
        async with httpx.AsyncClient(timeout=settings.MONOLITH_TIMEOUT_SECONDS) as client:
            response = await client.get(url)
    except httpx.HTTPError as exc:
        raise MonolithUnavailableError(str(exc)) from exc

    if response.status_code == 404:
        return None
    if response.status_code >= 400:
        raise MonolithUnavailableError(
            f"Monolith returned {response.status_code}: {response.text}"
        )

    data = response.json()
    try:
        seats_available = int(data["seats_available"])
        price = Decimal(str(data["price"]))
    except (KeyError, TypeError, ValueError, InvalidOperation) as exc:
        raise MonolithDataError("Monolith match payload is missing ticketing fields") from exc

    return {
        "match_id": int(data.get("match_id", match_id)),
        "seats_available": max(seats_available, 0),
        "unit_price": price,
        "currency": data.get("currency") or "RUB",
        "status": data.get("status"),
    }
