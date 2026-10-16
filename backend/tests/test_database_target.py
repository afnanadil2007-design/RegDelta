"""One database target: built from POSTGRES_*, never from DATABASE_URL, never leaked.

These cover the resolver itself, through the real settings and environment.
``test_database_guards`` runs the tools against a server with the same rules.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError
from sqlalchemy.engine import make_url

from app.core.config import (
    ADMIN_DATABASE,
    DatabaseConfigError,
    Settings,
    describe_database,
    get_settings,
    psycopg_args,
)

SECRET = "s3cret-Pa55"


def _settings(**overrides: object) -> Settings:
    return Settings(_env_file=None, **overrides)  # type: ignore[call-arg]


def test_the_postgres_parts_name_the_target() -> None:
    url = _settings(
        postgres_host="db.internal",
        postgres_port=6543,
        postgres_user="ana",
        postgres_password=SECRET,
        postgres_db="regdelta_x_test",
    ).database_target()
    assert url.drivername == "postgresql+psycopg"
    assert describe_database(url) == "ana@db.internal:6543/regdelta_x_test"
    assert psycopg_args(url) == {
        "host": "db.internal",
        "port": 6543,
        "user": "ana",
        "password": SECRET,
        "dbname": "regdelta_x_test",
    }
    # The administrative connection keeps the server and credentials only.
    assert psycopg_args(url, ADMIN_DATABASE)["dbname"] == ADMIN_DATABASE
    assert url.database == "regdelta_x_test"


@pytest.mark.parametrize(
    "database_url",
    [
        f"postgresql+psycopg://regdelta:{SECRET}@elsewhere:5432/regdelta",
        f"postgresql://u:{SECRET}@h/regdelta_x_test?sslmode=require&options=-csearch_path%3Dother",
        "not a url at all",
    ],
)
def test_a_database_url_is_refused_without_being_shown(database_url: str) -> None:
    # The test override names one database, the inherited URL another.
    settings = _settings(database_url=database_url, postgres_db="regdelta_x_test")
    with pytest.raises(DatabaseConfigError, match="DATABASE_URL is set") as refused:
        settings.database_target()
    assert SECRET not in str(refused.value) and "elsewhere" not in str(refused.value)
    assert SECRET not in repr(settings)


def test_an_empty_database_url_counts_as_unset() -> None:
    """The compose file sets DATABASE_URL="" for the api container."""
    url = _settings(database_url="", postgres_db="regdelta_x_test").database_target()
    assert url.database == "regdelta_x_test"


def test_the_environment_path_refuses_an_inherited_database_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DATABASE_URL", f"postgresql+psycopg://u:{SECRET}@h:5432/regdelta")
    monkeypatch.setenv("POSTGRES_DB", "regdelta_x_test")
    with pytest.raises(DatabaseConfigError) as refused:
        get_settings().database_target()
    assert SECRET not in str(refused.value)


@pytest.mark.parametrize(
    ("user", "password"),
    [
        ("ana", "p@ss:w/rd"),
        ("ana@corp", "100%sure?#&=+"),
        ("ana", "%41%2F%%"),  # already percent-encoded text is literal, not decoded
        ("ana", "spaces and é ü"),
    ],
)
def test_reserved_characters_keep_their_meaning(user: str, password: str) -> None:
    url = _settings(
        postgres_host="db.internal",
        postgres_port=6543,
        postgres_user=user,
        postgres_password=password,
        postgres_db="x_test",
    ).database_target()
    assert (url.username, url.password, url.host, url.port) == (user, password, "db.internal", 6543)
    args = psycopg_args(url)
    assert (args["user"], args["password"]) == (user, password)
    # Rendering and parsing back gives the same values (the encoding is exact).
    reparsed = make_url(url.render_as_string(hide_password=False))
    assert (reparsed.username, reparsed.password, reparsed.database) == (user, password, "x_test")
    assert password not in describe_database(url) and password not in str(url)


@pytest.mark.parametrize(
    ("overrides", "variable"),
    [
        ({"postgres_db": ""}, "POSTGRES_DB"),
        ({"postgres_db": "   "}, "POSTGRES_DB"),
        ({"postgres_db": "postgres"}, "POSTGRES_DB"),
        ({"postgres_db": "template1"}, "POSTGRES_DB"),
        ({"postgres_host": ""}, "POSTGRES_HOST"),
        ({"postgres_user": ""}, "POSTGRES_USER"),
    ],
)
def test_unusable_database_settings_are_refused(overrides: dict, variable: str) -> None:
    with pytest.raises(DatabaseConfigError, match=variable) as refused:
        _settings(postgres_password=SECRET, **overrides).database_target()
    assert SECRET not in str(refused.value)


@pytest.mark.parametrize("port", ["0", "70000", "abc"])
def test_an_invalid_port_fails_at_startup_without_the_password(
    monkeypatch: pytest.MonkeyPatch, port: str
) -> None:
    monkeypatch.setenv("POSTGRES_PORT", port)
    monkeypatch.setenv("POSTGRES_PASSWORD", SECRET)
    with pytest.raises(RuntimeError, match="postgres_port") as failed:
        get_settings()
    assert isinstance(failed.value.__cause__, ValidationError)
    assert SECRET not in str(failed.value)
