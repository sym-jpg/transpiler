from __future__ import annotations
import uuid
from dataclasses import dataclass


@dataclass(frozen=True)
class Trace:
    trace_id: str

    @staticmethod
    def new() -> "Trace":
        return Trace(trace_id=str(uuid.uuid4()))
