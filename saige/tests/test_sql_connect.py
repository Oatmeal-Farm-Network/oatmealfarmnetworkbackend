"""SQL connection helper: Cloud SQL Connector vs pymssql, no live DB."""
from types import SimpleNamespace

from config import DB_CONFIG
from data.sql.connect import rows_as_dicts, sql_configured, sql_connect, _connect_raw


def test_sql_configured_connector_without_host(monkeypatch):
    monkeypatch.setenv("INSTANCE_CONNECTION_NAME", "proj:us-central1:inst")
    monkeypatch.setitem(DB_CONFIG, "host", "")
    monkeypatch.setitem(DB_CONFIG, "user", "oatmeal_app")
    monkeypatch.setitem(DB_CONFIG, "database", "Oatmealailivedb")
    assert sql_configured() is True


def test_sql_configured_missing_creds_even_with_instance(monkeypatch):
    monkeypatch.setenv("INSTANCE_CONNECTION_NAME", "proj:us-central1:inst")
    monkeypatch.setitem(DB_CONFIG, "host", "")
    monkeypatch.setitem(DB_CONFIG, "user", "")
    monkeypatch.setitem(DB_CONFIG, "database", "")
    assert sql_configured() is False


def test_sql_configured_direct_host(monkeypatch):
    monkeypatch.delenv("INSTANCE_CONNECTION_NAME", raising=False)
    monkeypatch.setitem(DB_CONFIG, "host", "127.0.0.1")
    monkeypatch.setitem(DB_CONFIG, "user", "u")
    monkeypatch.setitem(DB_CONFIG, "database", "d")
    assert sql_configured() is True


def test_sql_configured_no_host_no_instance(monkeypatch):
    monkeypatch.delenv("INSTANCE_CONNECTION_NAME", raising=False)
    monkeypatch.setitem(DB_CONFIG, "host", "")
    monkeypatch.setitem(DB_CONFIG, "user", "u")
    monkeypatch.setitem(DB_CONFIG, "database", "d")
    assert sql_configured() is False


def test_sql_connect_returns_none_when_unconfigured(monkeypatch):
    monkeypatch.delenv("INSTANCE_CONNECTION_NAME", raising=False)
    monkeypatch.setitem(DB_CONFIG, "host", "")
    monkeypatch.setitem(DB_CONFIG, "user", "")
    monkeypatch.setitem(DB_CONFIG, "database", "")
    assert sql_connect() is None


def test_connect_raw_uses_pytds_connector(monkeypatch):
    monkeypatch.setenv("INSTANCE_CONNECTION_NAME", "proj:us-central1:inst")
    monkeypatch.setitem(DB_CONFIG, "user", "u")
    monkeypatch.setitem(DB_CONFIG, "password", "p")
    monkeypatch.setitem(DB_CONFIG, "database", "d")
    monkeypatch.setitem(DB_CONFIG, "host", "")
    seen = {}

    class FakeConnector:
        def connect(self, instance, driver, user, password, db):
            seen["args"] = (instance, driver, user, password, db)
            return object()

    monkeypatch.setattr("data.sql.connect._get_connector", lambda: FakeConnector())
    _connect_raw()
    assert seen["args"] == ("proj:us-central1:inst", "pytds", "u", "p", "d")


def test_rows_as_dicts_aliases_lowercase_keys():
    cursor = SimpleNamespace(description=(("BusinessID",), ("Name",)))
    rows = rows_as_dicts(cursor, [(9, "Alfalfa field 9")], as_dict=True)
    assert rows[0]["BusinessID"] == 9
    assert rows[0]["businessid"] == 9
    assert rows[0]["Name"] == "Alfalfa field 9"
    assert rows[0]["name"] == "Alfalfa field 9"


def test_rows_as_dicts_passthrough_when_not_as_dict():
    cursor = SimpleNamespace(description=(("BusinessID",),))
    rows = rows_as_dicts(cursor, [(9,)], as_dict=False)
    assert rows == [(9,)]
