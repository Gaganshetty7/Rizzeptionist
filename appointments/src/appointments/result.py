# Results can only be of type "success" or "failure".

from dataclasses import dataclass
from typing import Generic, TypeVar


T = TypeVar("T")

@dataclass(frozen=True)
class AppointmentResult(Generic[T]):
    success: bool
    data: T | None
    error_code: str | None
    message: str

    @classmethod
    def ok(
        cls,
        data: T,
        message: str = "Success",
    ) -> "AppointmentResult[T]":
        return cls(
            success=True,
            data=data,
            error_code=None,
            message=message,
        )

    @classmethod
    def failure(
        cls,
        error_code: str,
        message: str
    ) -> "AppointmentResult[None]":
        return cls(
            success=False,
            data=None,
            error_code=error_code,
            message=message,
        )
    
    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "data": self.data,
            "error_code": self.error_code,
            "message": self.message,
        }
    