"""Tracing (E3) with OpenTelemetry: one trace id flows from the browser request through the API, the graph
run, every node and LLM call, into every MCP server (via the MCP request `_meta`), and into the audit log.

Backend = any OTLP endpoint, chosen by standard env vars (no code change to switch):
  OTEL_EXPORTER_OTLP_TRACES_ENDPOINT=http://localhost:6006/v1/traces     self-hosted Arize Phoenix (compose)
  OTEL_EXPORTER_OTLP_TRACES_ENDPOINT / OTEL_EXPORTER_OTLP_HEADERS         Langfuse Cloud or LangSmith (OTLP)
  TRACE_URL_TEMPLATE=http://localhost:6006/redirects/traces/{trace_id}    link shown in the UI run viewer
No endpoint set -> tracing is off and every helper here is a cheap no-op.

Every span is passed through agent.pii.mask before export: emails, phones and payment details never leave.
"""
import functools
import inspect
import os
from contextlib import contextmanager

from opentelemetry import propagate, trace

from agent.pii import mask

TRACER = trace.get_tracer("gigbid")
_state = {"on": False}


def endpoint() -> str:
    return os.getenv("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT") or os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT") or ""


def setup_tracing(service: str) -> bool:
    """Call once per process (API, each MCP server). Safe to call when no endpoint is configured."""
    if _state["on"] or not endpoint():
        return _state["on"]
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    provider = TracerProvider(resource=Resource.create({"service.name": service,
                                                         "openinference.project.name": os.getenv("TRACE_PROJECT", "gigbid")}))
    provider.add_span_processor(BatchSpanProcessor(MaskingExporter(OTLPSpanExporter())))
    trace.set_tracer_provider(provider)
    try:                                   # LangGraph / LangChain spans (nodes, LLM calls with token counts)
        from openinference.instrumentation.langchain import LangChainInstrumentor
        LangChainInstrumentor().instrument(tracer_provider=provider)
    except Exception as e:  # noqa: BLE001 - tracing must never break the app
        print(f"tracing: LangChain instrumentation unavailable ({e})")
    _state["on"] = True
    return True


# ---------------------------------------------------------------- PII masking on export
def _clean(v):
    if isinstance(v, str):
        return mask(v)
    if isinstance(v, (list, tuple)):
        return type(v)(mask(x) if isinstance(x, str) else x for x in v)
    return v


try:
    from opentelemetry.sdk.trace import Event, ReadableSpan
    from opentelemetry.sdk.trace.export import SpanExporter

    class MaskingExporter(SpanExporter):
        """Wraps the real exporter and masks every string attribute and event attribute."""

        def __init__(self, inner: SpanExporter):
            self.inner = inner

        def export(self, spans):
            return self.inner.export([self._masked(s) for s in spans])

        @staticmethod
        def _masked(s: ReadableSpan) -> ReadableSpan:
            return ReadableSpan(
                name=s.name, context=s.context, parent=s.parent, resource=s.resource,
                attributes={k: _clean(v) for k, v in (s.attributes or {}).items()},
                events=[Event(e.name, {k: _clean(v) for k, v in (e.attributes or {}).items()}, e.timestamp) for e in s.events],
                links=s.links, kind=s.kind, status=s.status, start_time=s.start_time, end_time=s.end_time,
                instrumentation_scope=s.instrumentation_scope)

        def shutdown(self):
            return self.inner.shutdown()

        def force_flush(self, timeout_millis: int = 30000):
            return self.inner.force_flush(timeout_millis)
except ImportError:  # pragma: no cover - sdk is a dependency; keep import-safe anyway
    MaskingExporter = None


# ---------------------------------------------------------------- helpers used across the app
def current_trace_id() -> str | None:
    ctx = trace.get_current_span().get_span_context()
    return format(ctx.trace_id, "032x") if ctx.is_valid else None


def trace_url(trace_id: str | None) -> str | None:
    tpl = os.getenv("TRACE_URL_TEMPLATE", "")
    return tpl.format(trace_id=trace_id) if tpl and trace_id else None


def inject_meta() -> dict:
    """W3C trace context for an outgoing MCP call (sent in the request `_meta`)."""
    carrier: dict = {}
    propagate.inject(carrier)
    return carrier


@contextmanager
def span(name: str, parent_meta: dict | None = None, **attrs):
    """A span, optionally continuing a trace received from another process (MCP `_meta`)."""
    ctx = propagate.extract(parent_meta) if parent_meta else None
    with TRACER.start_as_current_span(name, context=ctx,
                                      attributes={k: v for k, v in attrs.items() if v is not None}) as sp:
        yield sp


def mcp_request_meta() -> dict:
    """Inside an MCP tool: the `_meta` the client sent (contains `traceparent` when tracing is on)."""
    try:
        from mcp.server.lowlevel.server import request_ctx
        meta = request_ctx.get().meta
        return meta.model_dump() if meta is not None else {}
    except Exception:  # noqa: BLE001 - called outside a request (unit tests)
        return {}


def traced_tool(server: str):
    """Decorator for MCP tools: continue the caller's trace and record one span per tool call."""
    def deco(fn):
        if inspect.iscoroutinefunction(fn):
            @functools.wraps(fn)
            async def awrap(*a, **kw):
                with span(f"mcp.{server}.{fn.__name__}", mcp_request_meta(), **{"mcp.server": server, "mcp.tool": fn.__name__}):
                    return await fn(*a, **kw)
            return awrap

        @functools.wraps(fn)
        def wrap(*a, **kw):
            with span(f"mcp.{server}.{fn.__name__}", mcp_request_meta(), **{"mcp.server": server, "mcp.tool": fn.__name__}):
                return fn(*a, **kw)
        return wrap
    return deco


def llm_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    """USD cost from config.yaml -> llm_pricing (per 1M tokens). Unknown or local models cost 0."""
    from agent.config import cfg
    p = (cfg().get("llm_pricing") or {}).get(model)
    if not p:
        return 0.0
    return round(input_tokens / 1e6 * p["input_per_m"] + output_tokens / 1e6 * p["output_per_m"], 6)
