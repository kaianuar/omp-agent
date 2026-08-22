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
        # provider-level scalar keys (baseUrl, apiKey): 4-space indent, no dash.
        # Skip 'models:' (the list header — the models list is built below).
        if (
            line.startswith("    ") and not line.startswith("      ")
            and ":" in line and not line.lstrip().startswith("-")
            and not line.strip().startswith("models:")
        ):
            k, _, v = line.strip().partition(":")
            result["providers"][current_provider][k.strip()] = v.strip()
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
            models.append({
                "id": m["id"],
                "name": m.get("name", m["id"]),
                "provider": (m["id"].split("/", 1)[0] if "/" in m["id"] else prov),
            })
    return models


def _list_models_api() -> list[dict[str, str]]:
    """Fetch model lists from EVERY provider omp is configured with.

    omp's models.yml can declare multiple providers, each with its own
    baseUrl + apiKey (all OpenAI-compatible). We hit GET /models on each
    and merge. Falls back to the OMP_LLM_* env vars, then CommandCode.
    """
    import httpx

    providers = _read_providers_yml()
    if not providers:
        # Env/CommandCode fallback (single provider).
        base = os.environ.get("OMP_LLM_BASE_URL", "https://api.commandcode.ai/provider/v1").rstrip("/")
        key = os.environ.get("OMP_LLM_API_KEY", os.environ.get("COMMANDCODE_API_KEY", ""))
        if key:
            providers = [{"name": "commandcode", "baseUrl": base, "apiKey": key}]

    out: list[dict[str, str]] = []
    for prov in providers:
        base = (prov.get("baseUrl") or "").rstrip("/")
        key = prov.get("apiKey") or ""
        if not base or not key:
            continue
        try:
            with httpx.Client(timeout=10) as client:
                resp = client.get(f"{base}/models", headers={"Authorization": f"Bearer {key}"})
                resp.raise_for_status()
                data = resp.json()
            models = data.get("data", data) if isinstance(data, dict) else data
            for m in models or []:
                mid = m.get("id") or m.get("name")
                if mid:
                    out.append({
                        "id": mid,
                        "name": m.get("name") or mid,
                        # provider = the id's prefix (before the first '/'),
                        # e.g. 'xiaomi/mimo-v2.5' → 'xiaomi'.
                        "provider": (mid.split("/", 1)[0] if "/" in mid else prov.get("name", "other")),
                    })
        except Exception:  # noqa: BLE001 — skip a broken provider, keep the rest
            continue
    # Dedupe by id (a model may appear on multiple providers).
    seen: set[str] = set()
    unique: list[dict[str, str]] = []
    for m in out:
        if m["id"] in seen:
            continue
        seen.add(m["id"])
        unique.append(m)
    return unique


def _read_providers_yml() -> list[dict[str, str]]:
    """Parse models.yml into [{name, baseUrl, apiKey}], one per provider."""
    yml = _read_yml(OMP_MODELS_YML)
    if not yml:
        return []
    providers: list[dict[str, str]] = []
    for name, conf in yml.get("providers", {}).items():
        entry = {"name": name}
        if conf.get("baseUrl"):
            entry["baseUrl"] = conf["baseUrl"]
        if conf.get("apiKey"):
            entry["apiKey"] = conf["apiKey"]
        providers.append(entry)
    return providers


def get_roles() -> dict[str, Any]:
    """Current role assignments + whether the user has configured them.

    roles are exactly what the user chose (no defaults merged in — the
    wizard forces an explicit pick for every role).
    """
    roles: dict[str, str] = {}
    if ROLES_FILE.exists():
        try:
            roles = json.loads(ROLES_FILE.read_text())
        except (json.JSONDecodeError, OSError):
            roles = {}
    configured = bool(roles)
    return {"configured": configured, "roles": roles, "defaults": ROLE_DEFAULTS}


def set_roles(roles: dict[str, str]) -> dict[str, Any]:
    """Persist role assignments. Requires ALL roles to be explicitly chosen.

    No defaults are applied — the user must pick a model for every role
    (the wizard forces this). Returns the updated config.
    """
    missing = [r for r in ROLE_DEFAULTS if not roles.get(r)]
    if missing:
        raise ValueError(f"all roles must be chosen, missing: {missing}")
    valid = {k: v for k, v in roles.items() if k in ROLE_DEFAULTS and v}
    ROLES_FILE.parent.mkdir(parents=True, exist_ok=True)
    ROLES_FILE.write_text(json.dumps(valid, indent=2))
    return get_roles()
