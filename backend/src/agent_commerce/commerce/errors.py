"""Stable commerce errors shared by REST and MCP transports."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class CommerceError(Exception):
    """A safe, machine-readable domain error."""

    code: str
    message: str
    details: dict[str, Any] | None = None

    def __str__(self) -> str:
        return self.message

    def as_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"code": self.code, "message": self.message}
        if self.details:
            payload["details"] = self.details
        return payload


def not_found(resource: str, resource_id: str) -> CommerceError:
    return CommerceError(
        code="NOT_FOUND",
        message=f"{resource} was not found",
        details={"resource": resource, "resource_id": resource_id},
    )


def conflict(message: str, **details: Any) -> CommerceError:
    return CommerceError(code="CONFLICT", message=message, details=details or None)


def validation_error(message: str, **details: Any) -> CommerceError:
    return CommerceError(code="VALIDATION_ERROR", message=message, details=details or None)

