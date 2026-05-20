import time

from fastapi import Request
from fastapi.responses import Response
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest

SERVICE_NAME = "auth_service"

HTTP_REQUESTS_TOTAL = Counter(
    "mik_http_requests_total",
    "Total HTTP requests handled by MIK services.",
    ["service", "method", "path", "status"],
)
HTTP_REQUEST_DURATION_SECONDS = Histogram(
    "mik_http_request_duration_seconds",
    "HTTP request duration in seconds for MIK services.",
    ["service", "method", "path"],
)
DOMAIN_EVENTS_TOTAL = Counter(
    "mik_domain_events_total",
    "Domain events emitted by MIK services.",
    ["service", "event"],
)


def route_path(request: Request) -> str:
    route = request.scope.get("route")
    return getattr(route, "path", request.url.path)


def record_http_request(method: str, path: str, status: int, duration: float) -> None:
    HTTP_REQUESTS_TOTAL.labels(
        service=SERVICE_NAME,
        method=method,
        path=path,
        status=str(status),
    ).inc()
    HTTP_REQUEST_DURATION_SECONDS.labels(
        service=SERVICE_NAME,
        method=method,
        path=path,
    ).observe(duration)


def record_domain_event(event: str) -> None:
    DOMAIN_EVENTS_TOTAL.labels(service=SERVICE_NAME, event=event).inc()


def metrics_response() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


async def metrics_middleware(request: Request, call_next):
    started_at = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        record_http_request(
            request.method,
            route_path(request),
            500,
            time.perf_counter() - started_at,
        )
        raise

    record_http_request(
        request.method,
        route_path(request),
        response.status_code,
        time.perf_counter() - started_at,
    )
    return response
