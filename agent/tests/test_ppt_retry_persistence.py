from src import ppt_service_v2 as ppt_service


class _FakeTable:
    def __init__(self):
        self.inserted = None

    def insert(self, payload):
        self.inserted = payload
        return self

    def execute(self):
        return {"ok": True}


class _FakeSupabase:
    def __init__(self):
        self.table_name = None
        self.table_obj = _FakeTable()

    def table(self, name):
        self.table_name = name
        return self.table_obj


def test_persist_failure_code_and_scope(monkeypatch):
    fake = _FakeSupabase()
    monkeypatch.setattr(ppt_service, "_get_supabase", lambda: fake)

    payload = {"failure_code": "timeout", "retry_scope": "slide"}
    ppt_service._persist_ppt_retry_diagnostic(payload)

    assert fake.table_name == "autoviralvid_ppt_retry_diagnostics"
    assert fake.table_obj.inserted["failure_code"] == "timeout"
    assert fake.table_obj.inserted["retry_scope"] == "slide"



