import time

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

import src.v7_routes as v7_routes


def _build_client() -> TestClient:
    app = FastAPI()
    app.include_router(v7_routes.router)
    return TestClient(app)


def _sample_export_request() -> dict:
    return {
        "slides": [
            {
                "page_number": 1,
                "slide_type": "cover",
                "markdown": "# 封面 <mark>重点</mark>",
                "script": [{"role": "host", "text": "封面讲解"}],
            }
        ]
    }


def _reset_v7_runtime_state(monkeypatch) -> None:
    monkeypatch.setattr(v7_routes, "_V7_SUPABASE_CLIENT", None)
    monkeypatch.setattr(v7_routes, "_V7_SUPABASE_INIT_ATTEMPTED", False)
    with v7_routes._V7_EXPORT_TASKS_LOCK:
        v7_routes._V7_EXPORT_TASKS.clear()


def test_v7_export_submit_and_status_success_local_background(monkeypatch):
    _reset_v7_runtime_state(monkeypatch)
    monkeypatch.setenv("PPT_EXECUTION_ROLE", "worker")
    monkeypatch.delenv("PPT_EXPORT_WORKER_BASE_URL", raising=False)
    monkeypatch.delenv("PPT_EXPORT_ALLOW_LOCAL_ASYNC_ON_WEB", raising=False)
    monkeypatch.delenv("PPT_EXPORT_WORKER_SHARED_SECRET", raising=False)
    monkeypatch.delenv("PPT_EXPORT_WORKER_REQUIRE_SIGNATURE", raising=False)

    async def _fake_execute(_req: dict) -> dict:
        return {
            "run_id": "run_local_1",
            "pptx_url": "https://example.com/presentation.pptx",
            "slide_count": 1,
        }

    monkeypatch.setattr(v7_routes, "_execute_export", _fake_execute)
    client = _build_client()

    submit_resp = client.post("/api/v1/v7/export/submit", json=_sample_export_request())
    assert submit_resp.status_code == 200
    submit_data = submit_resp.json()["data"]
    assert submit_data["status"] == "queued"
    assert submit_data["mode"] == "local_background"
    task_id = submit_data["task_id"]

    final_data = None
    for _ in range(50):
        status_resp = client.get(f"/api/v1/v7/export/status/{task_id}")
        assert status_resp.status_code == 200
        status_data = status_resp.json()["data"]
        if status_data["status"] == "succeeded":
            final_data = status_data
            break
        time.sleep(0.02)

    assert final_data is not None
    assert final_data["result"]["run_id"] == "run_local_1"


def test_v7_export_sync_is_disabled_by_default_on_web_role(monkeypatch):
    _reset_v7_runtime_state(monkeypatch)
    monkeypatch.setenv("PPT_EXECUTION_ROLE", "web")
    monkeypatch.delenv("PPT_EXPORT_SYNC_ENABLED", raising=False)

    called = {"value": False}

    async def _unexpected(_req: dict) -> dict:
        called["value"] = True
        return {"run_id": "should_not_happen"}

    monkeypatch.setattr(v7_routes, "_execute_export", _unexpected)
    client = _build_client()

    resp = client.post("/api/v1/v7/export", json=_sample_export_request())
    assert resp.status_code == 503
    assert "sync export is disabled on web role" in resp.json()["detail"]
    assert called["value"] is False


def test_v7_export_submit_uses_worker_proxy_when_configured(monkeypatch):
    _reset_v7_runtime_state(monkeypatch)
    monkeypatch.setenv("PPT_EXECUTION_ROLE", "web")
    monkeypatch.setenv("PPT_EXPORT_WORKER_BASE_URL", "https://worker.example.com")

    async def _fake_proxy_submit(_req: dict) -> dict:
        return {
            "task_id": "proxy-task-1",
            "status": "queued",
            "status_url": "/api/v1/v7/export/status/proxy-task-1",
        }

    monkeypatch.setattr(v7_routes, "_proxy_worker_submit", _fake_proxy_submit)
    client = _build_client()

    resp = client.post("/api/v1/v7/export/submit", json=_sample_export_request())
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["task_id"] == "proxy-task-1"
    assert data["mode"] == "proxy_worker"


def test_v7_export_submit_requires_signature_on_worker_when_enabled(monkeypatch):
    _reset_v7_runtime_state(monkeypatch)
    monkeypatch.setenv("PPT_EXECUTION_ROLE", "worker")
    monkeypatch.setenv("PPT_EXPORT_WORKER_SHARED_SECRET", "test-secret")
    monkeypatch.setenv("PPT_EXPORT_WORKER_REQUIRE_SIGNATURE", "true")

    async def _fake_execute(_req: dict) -> dict:
        return {"run_id": "run_signed_1", "slide_count": 1}

    monkeypatch.setattr(v7_routes, "_execute_export", _fake_execute)
    client = _build_client()
    body = _sample_export_request()

    denied = client.post("/api/v1/v7/export/submit", json=body)
    assert denied.status_code == 401

    signed_headers = v7_routes._build_worker_signature_headers(
        method="POST",
        path="/api/v1/v7/export/submit",
        body_payload=body,
    )
    submit = client.post("/api/v1/v7/export/submit", json=body, headers=signed_headers)
    assert submit.status_code == 200
    task_id = submit.json()["data"]["task_id"]

    status_headers = v7_routes._build_worker_signature_headers(
        method="GET",
        path=f"/api/v1/v7/export/status/{task_id}",
        body_payload=None,
    )
    status_resp = client.get(f"/api/v1/v7/export/status/{task_id}", headers=status_headers)
    assert status_resp.status_code == 200


def test_v7_export_task_can_be_loaded_from_supabase_when_memory_miss(monkeypatch):
    _reset_v7_runtime_state(monkeypatch)
    monkeypatch.setenv("PPT_EXECUTION_ROLE", "worker")
    monkeypatch.delenv("PPT_EXPORT_WORKER_SHARED_SECRET", raising=False)
    monkeypatch.delenv("PPT_EXPORT_WORKER_REQUIRE_SIGNATURE", raising=False)

    store = {}

    class _Res:
        def __init__(self, data):
            self.data = data

    class _Table:
        def __init__(self, rows):
            self._rows = rows
            self._task_id = None
            self._op = ""
            self._row = None

        def upsert(self, row):
            self._op = "upsert"
            self._row = dict(row)
            return self

        def select(self, *_args):
            self._op = "select"
            return self

        def eq(self, key, value):
            if key == "task_id":
                self._task_id = value
            return self

        def limit(self, _value):
            return self

        def execute(self):
            if self._op == "upsert":
                self._rows[self._row["task_id"]] = dict(self._row)
                return _Res([dict(self._row)])
            if self._op == "select" and self._task_id:
                row = self._rows.get(self._task_id)
                return _Res([dict(row)] if row else [])
            return _Res([])

    class _SB:
        def __init__(self, rows):
            self._rows = rows

        def table(self, _name):
            return _Table(self._rows)

    fake_sb = _SB(store)
    monkeypatch.setattr(v7_routes, "_get_supabase_client", lambda: fake_sb)

    task_id = "task-db-1"
    v7_routes._put_export_task(
        task_id,
        {
            "task_id": task_id,
            "status": "queued",
            "mode": "local_background",
            "runtime_role": "worker",
            "request_meta": {"slide_count": 1},
            "created_at": "2026-03-30T00:00:00+00:00",
        },
    )
    assert task_id in store

    with v7_routes._V7_EXPORT_TASKS_LOCK:
        v7_routes._V7_EXPORT_TASKS.clear()

    loaded = v7_routes._get_export_task(task_id)
    assert loaded is not None
    assert loaded["task_id"] == task_id
    assert loaded["status"] == "queued"


@pytest.mark.asyncio
async def test_v7_execute_export_forces_deck_scope_and_local_channel(monkeypatch):
    import src.minimax_exporter as minimax_exporter
    import src.pptx_rasterizer as pptx_rasterizer
    import src.r2 as r2

    calls = []

    def _fake_export(**kwargs):
        calls.append(dict(kwargs))
        return {
            "pptx_bytes": b"v7-pptx",
            "generator_meta": {"render_slides": 1},
            "render_spec": {
                "mode": "minimax_presentation",
                "slides": [{"slide_id": "s1", "slide_type": "cover"}],
            },
            "input_payload": {"slides": [{"slide_id": "s1"}]},
        }

    async def _fake_upload(_bytes, key, content_type):
        return f"https://example.com/{key}"

    monkeypatch.setattr(minimax_exporter, "export_minimax_pptx", _fake_export)
    monkeypatch.setattr(r2, "upload_bytes_to_r2", _fake_upload)
    monkeypatch.setattr(
        pptx_rasterizer, "rasterize_pptx_bytes_to_png_bytes", lambda _pptx: []
    )

    body = _sample_export_request()
    body.update(
        {
            "retry_scope": "slide",
            "target_slide_ids": ["s1"],
            "target_block_ids": ["b1"],
        }
    )
    data = await v7_routes._execute_export(body)

    assert data["run_id"]
    assert data["slide_count"] == 1
    assert calls
    assert calls[0]["retry_scope"] == "deck"
    assert calls[0]["target_slide_ids"] == []
    assert calls[0]["target_block_ids"] == []
    assert calls[0]["render_channel"] == "local"
