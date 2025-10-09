from functools import wraps
from opentelemetry import trace
from typing import Any, Callable, TypeVar, cast

T = TypeVar("T")


def instrument_method(span_name: str = None):
    """Decorator to add OpenTelemetry instrumentation to methods.

    Args:
        span_name (str, optional): Name for the span. If not provided, uses the method name.
    """

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        def wrapper(self, *args: Any, **kwargs: Any) -> T:
            tracer = trace.get_tracer(func.__module__)
            name = span_name or func.__name__

            with tracer.start_as_current_span(name) as span:
                # Add class name and method name as attributes
                span.set_attribute("class", self.__class__.__name__)
                span.set_attribute("method", func.__name__)

                # Add project_id if available
                if hasattr(self, "project"):
                    span.set_attribute("project_id", str(self.project.id))

                # Execute the original method
                result = func(self, *args, **kwargs)

                return result

        return cast(Callable[..., T], wrapper)

    return decorator


def instrument_span(span_name: str):
    """Context manager for creating a span within a method.

    Args:
        span_name (str): Name for the span
    """
    tracer = trace.get_tracer(__name__)
    return tracer.start_as_current_span(span_name)
