"""Role/model configuration for the webapp.

Reads the model list from omp's own config (`~/.omp/agent/models.yml`) so
the web UI shows exactly the models omp has. Role assignments (which model
plays orchestrator / builder / critic) are persisted locally in a JSON file
(next to the DB), so the setup wizard only shows once and settings can
change them later.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

# ── paths ──────────────────────────────────────────────────────────────

OMP_MODELS_YML = Path(os.environ.get("OMP_MODELS_YML", "~/.omp/agent/models.yml")).expanduser()
ROLES_FILE = Path(__file__).resolve().parent.parent / "data" / "roles.json"

# The three roles the webapp needs assigned.
# Defaults MUST be models that actually exist on the provider. muse-spark
# IS a CommandCode model (meta/muse-spark-1.2-contributor — confirmed on the
# live API), even though it's absent from omp's models.yml (a partial list).
ROLE_DEFAULTS = {
    "orchestrator": "xiaomi/mimo-v2.5",          # brain: intake/design/recipe
    "builder": "xiaomi/mimo-v2.5-pro",           # writes code
    "critic": "meta/muse-spark-1.2-contributor", # adversarial review
}


def _read_yml(path: Path) -> dict[str, Any] | None:
    """Minimal YAML-ish parse of models.yml (provider + model list).

    omp's models.yml is a flat structure:
      providers:
        commandcode:
          api: openai-completions
          baseUrl: https://...
          models:
          - id: xiaomi/mimo-v2.5
            name: MiMo V2.5
            contextWindow: ...
    We only need providers → models (id/name). A full YAML parser is a dep
    we don't want; this handles the indented list shape.
    """
    try:
        text = path.read_text()
    except OSError:
        return None
    result: dict[str, Any] = {"providers": {}}
    current_provider: str | None = None
    current_model: dict[str, str] | None = None
    for line in text.splitlines():
        stripped = line.rstrip()
        if stripped.startswith("providers:"):
            continue
        # provider block: 2-space indent + name + colon
        if line.startswith("  ") and not line.startswith("    ") and line.strip().endswith(":"):
            current_provider = line.strip()[:-1]
            result["providers"][current_provider] = {"models": []}
            current_model = None
            continue
        if current_provider is None:
            continue
        # model entry: 4-space indent + "- id:"
        if line.startswith("    - id:"):
            mid = line.split(":", 1)[1].strip()
            current_model = {"id": mid, "name": mid}
            result["providers"][current_provider]["models"].append(current_model)
            continue
        if current_model is not None and line.startswith("      name:"):
            current_model["name"] = line.split(":", 1)[1].strip()
            continue
    return result


def list_models() -> list[dict[str, str]]:
    """All models the provider has — live API first, models.yml fallback.

    omp's models.yml is a partial/filtered list; the provider's /models
    endpoint is the source of truth (e.g. muse-spark-1.2-contributor exists
    on the API but not in models.yml). Falls back to models.yml when the
    API is unreachable.
    """
    live = _list_models_api()
    if live:
        return live
    yml = _read_yml(OMP_MODELS_YML)
    if not yml:
        return []
    models: list[dict[str, str]] = []
    for prov, conf in yml.get("providers", {}).items():
        for m in conf.get("models", []):
            models.append({"id": m["id"], "name": m.get("name", m["id"])})
    return models


def _list_models_api() -> list[dict[str, str]]:
    """Fetch the provider's model list via the OpenAI-compatible /models."""
    import httpx

    base = os.environ.get("OMP_LLM_BASE_URL", "https://api.commandcode.ai/provider/v1").rstrip("/")
    key = os.environ.get("OMP_LLM_API_KEY", os.environ.get("COMMANDCODE_API_KEY", ""))
    if not key:
        return []
    try:
        with httpx.Client(timeout=10) as client:
            resp = client.get(f"{base}/models", headers={"Authorization": f"Bearer {key}"})
            resp.raise_for_status()
            data = resp.json()
        models = data.get("data", data) if isinstance(data, dict) else data
        out: list[dict[str, str]] = []
        for m in models or []:
            mid = m.get("id") or m.get("name")
            if mid:
                out.append({"id": mid, "name": m.get("name") or mid})
        # Dedupe by id (API may repeat).
        seen: set[str] = set()
        unique: list[dict[str, str]] = []
        for m in out:
            if m["id"] in seen:
                continue
            seen.add(m["id"])
            unique.append(m)
        return unique
    except Exception:  # noqa: BLE001 — fall back to models.yml
        return []


def get_roles() -> dict[str, Any]:
    """Current role assignments + whether the user has configured them."""
    roles: dict[str, str] = {}
    if ROLES_FILE.exists():
        try:
            roles = json.loads(ROLES_FILE.read_text())
        except (json.JSONDecodeError, OSError):
            roles = {}
    configured = bool(roles)
    merged = {**ROLE_DEFAULTS, **roles}  # defaults fill unset roles
    return {"configured": configured, "roles": merged, "defaults": ROLE_DEFAULTS}


def set_roles(roles: dict[str, str]) -> dict[str, Any]:
    """Persist role assignments. Returns the updated config."""
    valid = {k: v for k, v in roles.items() if k in ROLE_DEFAULTS and v}
    ROLES_FILE.parent.mkdir(parents=True, exist_ok=True)
    ROLES_FILE.write_text(json.dumps({**get_roles()["roles"], **valid}, indent=2))
    return get_roles()
