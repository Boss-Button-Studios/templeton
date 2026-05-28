"""
Agent result schema validator for the Templeton harness.

Validates one result dict against the Section 5 schema.
Raises ValidationError with a human-readable message on any failure.
"""

import uuid as _uuid_mod

SCHEMA_VERSION = "1.0"

VALID_FLAG_IDS = frozenset(
    {"F-01", "F-02", "F-03", "F-04", "F-05", "F-06", "F-07"}
)
VALID_TERMINATION_REASONS = frozenset(
    {"success", "budget_exhausted", "no_path_found", "error"}
)


class ValidationError(Exception):
    """A result object failed schema validation."""


def validate(result: dict, expected_run_id: str | None = None) -> None:
    """
    Validate one agent result object against the Section 5 schema.

    Args:
        result:          Parsed JSON dict from the agent.
        expected_run_id: If provided, the result's run_id must match.

    Raises:
        ValidationError: with a human-readable message on the first failure found.
    """
    _req_str(result, "schema_version")
    if result["schema_version"] != SCHEMA_VERSION:
        raise ValidationError(
            f"schema_version {result['schema_version']!r} is not supported; "
            f"expected {SCHEMA_VERSION!r}"
        )

    _req_str(result, "run_id")
    try:
        _uuid_mod.UUID(result["run_id"])
    except ValueError:
        raise ValidationError("run_id is not a valid UUID")
    if expected_run_id and result["run_id"] != expected_run_id:
        raise ValidationError(
            f"run_id mismatch — result has {result['run_id']!r}, "
            f"expected {expected_run_id!r}"
        )

    _req_str(result, "agent_name")
    _req_str(result, "agent_version")

    _req_str(result, "target_flag_id")
    if result["target_flag_id"] not in VALID_FLAG_IDS:
        raise ValidationError(
            f"target_flag_id {result['target_flag_id']!r} is not a known flag; "
            f"must be one of {sorted(VALID_FLAG_IDS)}"
        )

    _req_bool(result, "found")

    if result["found"]:
        if result.get("extracted_value") is None:
            raise ValidationError("extracted_value is required when found=true")
        if not result.get("source_url"):
            raise ValidationError("source_url is required when found=true")

    cs = result.get("confidence_score")
    if cs is None:
        raise ValidationError("confidence_score is required")
    if not isinstance(cs, (int, float)) or not (0.0 <= float(cs) <= 1.0):
        raise ValidationError(
            "confidence_score must be a number between 0.0 and 1.0"
        )

    _req_str(result, "termination_reason")
    if result["termination_reason"] not in VALID_TERMINATION_REASONS:
        raise ValidationError(
            f"termination_reason {result['termination_reason']!r} is not valid; "
            f"must be one of {sorted(VALID_TERMINATION_REASONS)}"
        )

    _req_nonneg_int(result, "pages_visited")
    _req_nonneg_int(result, "depth_reached")
    _req_bool(result, "budget_exhausted")

    if "best_candidate_url" not in result:
        raise ValidationError("best_candidate_url is required (may be null)")
    bcu = result["best_candidate_url"]
    if bcu is not None and not isinstance(bcu, str):
        raise ValidationError("best_candidate_url must be a string or null")

    if "visit_log" not in result:
        raise ValidationError("visit_log is required")
    if not isinstance(result["visit_log"], list):
        raise ValidationError("visit_log must be an array")
    for i, entry in enumerate(result["visit_log"]):
        if not isinstance(entry, dict):
            raise ValidationError(f"visit_log[{i}] must be an object")
        for key in ("url", "depth", "outcome"):
            if key not in entry:
                raise ValidationError(f"visit_log[{i}].{key} is required")


# ── field-level helpers ───────────────────────────────────────────────────────

def _req_str(d: dict, key: str) -> None:
    if key not in d:
        raise ValidationError(f"{key!r} is required")
    if not isinstance(d[key], str):
        raise ValidationError(f"{key!r} must be a string, got {type(d[key]).__name__}")
    if not d[key].strip():
        raise ValidationError(f"{key!r} must not be empty")


def _req_bool(d: dict, key: str) -> None:
    if key not in d:
        raise ValidationError(f"{key!r} is required")
    if not isinstance(d[key], bool):
        raise ValidationError(f"{key!r} must be a boolean")


def _req_nonneg_int(d: dict, key: str) -> None:
    if key not in d:
        raise ValidationError(f"{key!r} is required")
    if not isinstance(d[key], int) or isinstance(d[key], bool) or d[key] < 0:
        raise ValidationError(f"{key!r} must be a non-negative integer")
