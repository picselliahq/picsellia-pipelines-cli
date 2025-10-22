from datetime import datetime

from picsellia import Client


def extract_job_and_run_ids(resp: dict) -> tuple[str | None, str | None]:
    job_id, run_id = None, None
    if isinstance(resp, dict):
        job_id = (
            resp.get("job_id") or resp.get("id") or (resp.get("job") or {}).get("id")
        )
        runs = resp.get("runs") or []
        latest_run = _pick_latest_run(runs) if isinstance(runs, list) else None
        if latest_run and isinstance(latest_run, dict):
            run_id = latest_run.get("id")
        if not run_id:
            run_id = resp.get("run_id") or (resp.get("run") or {}).get("id")
    return job_id, run_id


def build_job_url(client: Client, job_id: str, run_id: str | None) -> str:
    base = client.connexion.host.rstrip("/")
    org_id = getattr(client.connexion, "organization_id", None)
    if run_id:
        return f"{base}/{org_id}/jobs/{job_id}/runs/{run_id}"
    return f"{base}/{org_id}/jobs/{job_id}"


def _parse_dt(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:
        return None


def _pick_latest_run(runs: list[dict]) -> dict | None:
    if not runs:
        return None

    def key(r: dict) -> datetime:
        return (
            _parse_dt(r.get("updated_at"))
            or _parse_dt(r.get("created_at"))
            or datetime.min
        )

    return max(runs, key=key)
