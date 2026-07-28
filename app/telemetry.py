from app.config import Settings


from typing import Optional

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.requests import RequestsInstrumentor
from starlette.routing import Match
from opentelemetry.instrumentation.fastapi import otel_fastapi


def _patch_fastapi_route_details() -> None:
    """
    opentelemetry-instrumentation-fastapi==0.63b1's _get_route_details() guards
    AttributeError only on the Match.FULL branch, not Match.PARTIAL. FastAPI
    >=0.137 wraps include_router()'d routers in _IncludedRouter, which lacks
    a .path attribute and matches as PARTIAL for most requests, crashing every
    request with AttributeError. Fixed upstream in 0.64b0, but that version
    requires opentelemetry-sdk>=1.43 which conflicts with logfire (pulled in
    via pydantic-ai) capping it at <1.43. Patch locally until that's resolved.
    """

    def _get_route_details(scope):
        app = scope["app"]
        route = None

        for starlette_route in app.routes:
            match, _ = starlette_route.matches(scope)
            if match == Match.FULL:
                route = getattr(starlette_route, "path", scope.get("path"))
                break
            if match == Match.PARTIAL:
                route = getattr(starlette_route, "path", route)
        return route

    otel_fastapi._get_route_details = _get_route_details


def setup_tracing(endpoint: Optional[str] = None):
    # Manually create a fresh, uncached Settings instance
    settings = Settings()

    if endpoint is None:
        endpoint = settings.otel_exporter_otlp_endpoint

    # Resource can be required for some backends, e.g. Jaeger
    # If resource wouldn't be set - traces wouldn't appears in Jaeger
    resource = Resource(attributes={"service.name": settings.otel_service_name})

    tracer_provider = TracerProvider(resource=resource)
    trace.set_tracer_provider(tracer_provider)

    otlp_exporter = OTLPSpanExporter(endpoint=endpoint, insecure=True)

    span_processor = BatchSpanProcessor(otlp_exporter)
    tracer_provider.add_span_processor(span_processor)

    RequestsInstrumentor().instrument()

    return tracer_provider
