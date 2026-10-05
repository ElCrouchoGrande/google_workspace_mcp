"""Coverage for the fork's public pages and the /auth/joint route in core.server."""

from types import SimpleNamespace
import pytest
from starlette.requests import Request

import core.server as server_module
from core.server import (
    health_check,
    homepage,
    initiate_joint_auth,
    privacy_policy,
    terms_of_service,
)


def _request(path: str) -> Request:
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": path,
            "raw_path": path.encode(),
            "query_string": b"",
            "headers": [],
        }
    )


def _routes() -> dict:
    return {
        route.path: route.endpoint
        for route in server_module.server._get_additional_http_routes()
    }


def test_root_path_serves_homepage_not_health_check():
    routes = _routes()
    assert routes["/"] is homepage
    assert routes["/health"] is health_check
    assert routes["/privacy"] is privacy_policy
    assert routes["/terms"] is terms_of_service
    assert routes["/auth/joint"] is initiate_joint_auth


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "handler, path, expected",
    [
        (homepage, "/", "Paul's Daily Assistant"),
        (privacy_policy, "/privacy", "Privacy Policy"),
        (terms_of_service, "/terms", "Terms of Service"),
    ],
)
async def test_public_pages_render_html(handler, path, expected):
    response = await handler(_request(path))
    assert response.status_code == 200
    assert response.media_type == "text/html"
    assert expected in response.body.decode()


@pytest.mark.asyncio
async def test_homepage_links_to_privacy_and_terms():
    body = (await homepage(_request("/"))).body.decode()
    assert 'href="/privacy"' in body
    assert 'href="/terms"' in body


class _FakeFlow:
    code_verifier = "verifier-123"

    def authorization_url(self, **kwargs):
        self.kwargs = kwargs
        return "https://accounts.google.com/o/oauth2/auth?state=abc", "abc"


@pytest.mark.asyncio
async def test_auth_joint_redirects_to_google_with_joint_login_hint(monkeypatch):
    flow = _FakeFlow()
    stored = {}
    store = SimpleNamespace(
        store_oauth_state=lambda state, **kwargs: stored.update(state=state, **kwargs)
    )
    captured = {}

    def fake_create_oauth_flow(**kwargs):
        captured.update(kwargs)
        return flow

    import auth.google_auth as google_auth
    import auth.oauth21_session_store as session_store

    monkeypatch.setattr(google_auth, "create_oauth_flow", fake_create_oauth_flow)
    monkeypatch.setattr(session_store, "get_oauth21_session_store", lambda: store)
    monkeypatch.setattr(
        server_module,
        "get_oauth_redirect_uri_for_current_mode",
        lambda: "https://example.test/oauth2callback",
    )

    response = await initiate_joint_auth(_request("/auth/joint"))

    assert response.status_code == 200
    assert flow.kwargs["login_hint"] == "lizzieandpaul2019@gmail.com"
    assert flow.kwargs["access_type"] == "offline"
    assert captured["redirect_uri"] == "https://example.test/oauth2callback"
    assert stored["code_verifier"] == "verifier-123"
    assert stored["session_id"] is None
    assert stored["state"] == captured["state"]
    assert "accounts.google.com" in response.body.decode()


@pytest.mark.asyncio
async def test_auth_joint_reports_failure_as_500(monkeypatch):
    import auth.google_auth as google_auth

    def boom(**kwargs):
        raise RuntimeError("no client secrets")

    monkeypatch.setattr(google_auth, "create_oauth_flow", boom)
    monkeypatch.setattr(
        server_module, "get_oauth_redirect_uri_for_current_mode", lambda: "https://x"
    )

    response = await initiate_joint_auth(_request("/auth/joint"))
    assert response.status_code == 500
    assert "no client secrets" in response.body.decode()
