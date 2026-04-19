"""Observability primitives — structured logging helpers, metrics, and the
in-process :class:`TraceBus` used for live agent-trace streaming to the UI.
"""

from .trace_bus import (
    TraceBus,
    emit_step,
    get_trace_id,
    set_trace_id,
    trace_scope,
    get_bus,
)

__all__ = [
    "TraceBus",
    "emit_step",
    "get_trace_id",
    "set_trace_id",
    "trace_scope",
    "get_bus",
]
