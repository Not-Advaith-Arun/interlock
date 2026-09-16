"""Strict local JSON input and content fingerprints, with no dynamic imports."""

import hashlib
import json
from pathlib import Path
from typing import Any

from .models import MODELS

VERSIONS = ("base", "left", "right", "merged")
MAX_INPUT_BYTES = 2_000_000
# A witness embeds the scenario and may expand Unicode into ASCII escapes.
# Keep scenario ingestion at 2 MB while allowing generated witnesses to round-trip.
MAX_WITNESS_BYTES = 16_000_000


def canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)


def fingerprint(scenario: dict) -> str:
    return hashlib.sha256(canonical(scenario).encode()).hexdigest()


def validate_scenario(value: Any) -> dict:
    if not isinstance(value, dict) or set(value) != {"format", "name", "model", "versions"}:
        raise ValueError("scenario requires exactly format, name, model, and versions")
    if value["format"] != "interlock-scenario-v1":
        raise ValueError("unsupported scenario format")
    if not isinstance(value["name"], str) or not value["name"] or len(value["name"]) > 200:
        raise ValueError("name must be a nonempty string of at most 200 characters")
    if not isinstance(value["model"], str) or value["model"] not in MODELS:
        raise ValueError("model must be retry-v1 or fsm-v1")
    versions = value["versions"]
    if not isinstance(versions, dict) or set(versions) != set(VERSIONS):
        raise ValueError("versions must contain exactly base, left, right, and merged")
    for version in VERSIONS:
        config = versions[version]
        if not isinstance(config, dict):
            raise ValueError(f"{version} config must be an object")
        try:
            MODELS[value["model"]].validate(config)
        except ValueError as exc:
            raise ValueError(f"{version}: {exc}") from exc
    return value


def _unique_object(pairs: list[tuple[str, Any]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON field: {key}")
        result[key] = value
    return result


def read_json(path: str | Path, *, max_bytes: int = MAX_INPUT_BYTES) -> Any:
    if type(max_bytes) is not int or max_bytes < 1:
        raise ValueError("input size limit must be a positive integer")
    with Path(path).open("rb") as stream:
        raw = stream.read(max_bytes + 1)
    if len(raw) > max_bytes:
        raise ValueError(f"input exceeds {max_bytes / 1_000_000:g} MB limit")
    def reject_constant(value: str) -> None:
        raise ValueError(f"invalid JSON constant: {value}")
    return json.loads(raw, object_pairs_hook=_unique_object, parse_constant=reject_constant)
