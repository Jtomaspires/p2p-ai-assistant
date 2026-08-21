"""Shared helpers for workflow nodes."""

from app.domain.context import ProcessingContext
from app.domain.deps import WorkflowDeps
from app.domain.results import NodeResult


def require_deps(context: ProcessingContext) -> WorkflowDeps:
    if context.deps is None:
        raise RuntimeError("ProcessingContext.deps is not set")
    return context.deps


def finish(context: ProcessingContext, result: NodeResult) -> ProcessingContext:
    context.last_result = result
    if result.stop_pipeline:
        context.stop_workflow()
    return context


def sender_domain(email: str) -> str:
    return email.rsplit("@", 1)[-1].lower() if "@" in email else email.lower()
