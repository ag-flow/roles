"""NDJSON event emitter on stdout (contract: spec 03 § Format des events NDJSON)."""
from __future__ import annotations

import json
import sys
from typing import Any


def emit(event_type: str, **fields: Any) -> None:
    """Write one NDJSON event line to stdout and flush immediately.

    Format: {"type": <event_type>, ...fields}
    Always one event per line (NDJSON).
    """
    payload = {"type": event_type, **fields}
    sys.stdout.write(json.dumps(payload) + "\n")
    sys.stdout.flush()
