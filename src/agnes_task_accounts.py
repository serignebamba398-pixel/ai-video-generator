"""Resume shared video tasks using their original Agnes account."""

import copy
import hashlib
import json
import os

from src.agnes_client import AgnesAPIError


def account_fingerprint(client):
    key = getattr(client, "api_key", None)
    return hashlib.sha256(key.encode()).hexdigest() if isinstance(key, str) and key else None


def wait_for_saved_task(client, task_path, **kwargs):
    try:
        data = json.loads(task_path.read_text(encoding="utf-8"))
        owner = data.get("account_fingerprint")
    except (OSError, ValueError, AttributeError):
        owner = None

    candidates = [client]
    seen = {getattr(client, "api_key", None)}
    for name in ("AGNES_API_KEY", "AGNES_API_KEY2"):
        key = os.getenv(name)
        if not key or key in seen:
            continue
        seen.add(key)
        candidate = copy.copy(client)
        candidate.api_key = key
        candidate.headers = {**client.headers, "Authorization": f"Bearer {key}"}
        candidates.append(candidate)

    if owner:
        candidates = [candidate for candidate in candidates if account_fingerprint(candidate) == owner]
        if not candidates:
            raise AgnesAPIError(
                "La clé Agnes ayant créé cette tâche n'est plus configurée. "
                "Restaure cette clé dans .env pour reprendre la tâche."
            )

    for index, candidate in enumerate(candidates):
        try:
            return candidate.wait_for_video(**kwargs)
        except AgnesAPIError as exc:
            # Old tasks have no owner metadata. Only a missing-task response
            # permits trying another account; never submit a replacement here.
            if owner or exc.status_code != 404 or index == len(candidates) - 1:
                raise

