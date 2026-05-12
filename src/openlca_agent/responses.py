from __future__ import annotations

from collections.abc import Callable
from typing import Any

from pydantic import BaseModel

from openlca_agent.models import to_plain


def ok(data: Any | None = None) -> dict[str, Any]:
    return {"ok": True, "data": to_plain(data) if data is not None else {}}


def error(
    error_code: str,
    message: str,
    remediation: str,
    data: Any | None = None,
) -> dict[str, Any]:
    response: dict[str, Any] = {
        "ok": False,
        "error_code": error_code,
        "message": message,
        "remediation": remediation,
    }
    if data is not None:
        response["data"] = to_plain(data)
    return response


def normalize_exception(exc: Exception) -> dict[str, Any]:
    message = str(exc) or exc.__class__.__name__
    lowered = message.lower()
    if isinstance(exc, ConnectionError) or "connection" in lowered or "refused" in lowered:
        return error(
            "OPENLCA_IPC_UNAVAILABLE",
            message,
            "Start openLCA Desktop, open the target database, then start "
            "the IPC Server on port 8080.",
        )
    if isinstance(exc, FileNotFoundError):
        return error("FILE_NOT_FOUND", message, "Check the provided file path and try again.")
    if isinstance(exc, ValueError):
        return error("VALIDATION_ERROR", message, "Fix the input data and retry the tool call.")
    return error(
        "OPENLCA_AGENT_ERROR",
        message,
        "Check the openLCA-Agent logs and retry with a smaller, explicit input.",
    )


def guarded(fn: Callable[[], Any]) -> dict[str, Any]:
    try:
        result = fn()
        if isinstance(result, dict) and "ok" in result:
            return result
        if isinstance(result, BaseModel):
            return ok(result)
        return ok(result)
    except Exception as exc:  # noqa: BLE001 - MCP tools should return structured errors.
        return normalize_exception(exc)
