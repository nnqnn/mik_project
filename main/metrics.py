import time

from django.http import HttpResponse
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest

SERVICE_NAME = "django_monolith"

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


def _request_path(request):
    resolver_match = getattr(request, "resolver_match", None)
    route = getattr(resolver_match, "route", None)
    if route == "":
        return "/"
    return f"/{route}" if route else request.path


def record_domain_event(event: str) -> None:
    DOMAIN_EVENTS_TOTAL.labels(service=SERVICE_NAME, event=event).inc()


def metrics_view(request):
    return HttpResponse(generate_latest(), content_type=CONTENT_TYPE_LATEST)


class MetricsMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        started_at = time.perf_counter()
        try:
            response = self.get_response(request)
        except Exception:
            duration = time.perf_counter() - started_at
            path = _request_path(request)
            HTTP_REQUESTS_TOTAL.labels(
                service=SERVICE_NAME,
                method=request.method,
                path=path,
                status="500",
            ).inc()
            HTTP_REQUEST_DURATION_SECONDS.labels(
                service=SERVICE_NAME,
                method=request.method,
                path=path,
            ).observe(duration)
            raise

        duration = time.perf_counter() - started_at
        path = _request_path(request)
        HTTP_REQUESTS_TOTAL.labels(
            service=SERVICE_NAME,
            method=request.method,
            path=path,
            status=str(response.status_code),
        ).inc()
        HTTP_REQUEST_DURATION_SECONDS.labels(
            service=SERVICE_NAME,
            method=request.method,
            path=path,
        ).observe(duration)
        return response
