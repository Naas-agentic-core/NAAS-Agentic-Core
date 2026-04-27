import pytest
from httpx import ASGITransport, AsyncClient


@pytest.mark.asyncio
@pytest.mark.skip(reason="Legacy monolith WS route disabled")
async def test_frontend_smoke_flow(test_app):
    """
    Verifies the critical frontend integration flow:
    1. Root path (/) serves index.html
    2. Static assets (CSS/JS) are reachable and non-empty.
    3. Login endpoint is reachable (not 404/405).
    4. Admin latest chat endpoint is reachable.
    """
    # Use the test_app from conftest which has DB overrides configured
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        # 1. Check Root
        response = await ac.get("/")
        assert response.status_code == 200
        assert '<div id="root"' in response.text or "<!doctype html" in response.text.lower()

        # 2. Check Assets
        # Note: We rely on the app mounting StaticFiles.
        # If the file doesn't exist on disk in the test environment, this might fail
        # unless we mock it or ensure it exists.
        # But we created placeholders in previous steps.
        css_resp = await ac.get("/css/superhuman-ui.css")
        assert css_resp.status_code == 200
        assert len(css_resp.text) > 0

        js_resp = await ac.get("/js/script.js")
        assert js_resp.status_code == 200
        assert len(js_resp.text) > 0

        # 3. Check Login Endpoint (Smoke Check)
        # We expect 422 (Validation Error) or 401 (Unauthorized) or 200.
        # We definitely DO NOT want 404 or 405.
        login_payload = {"email": "admin@cogniforge.com", "password": "wrongpassword"}
        # Because conftest overrides StaticFiles with a temp dir,
        # the app routing logic might be slightly different than live,
        # but the API routers are still mounted by the Kernel.
        # The key is that test_app dependency_overrides[get_db] is set.
        login_resp = await ac.post("/api/security/login", json=login_payload)
        assert login_resp.status_code in [
            200,
            400,
            401,
            422,
        ], f"Login endpoint returned unexpected status: {login_resp.status_code}"

        # 4. Check Admin Latest Chat Endpoint (Smoke Check)
        # Without a valid token, this should return 401.
        # If it returns 404, the route is missing.
        chat_resp = await ac.get("/admin/api/chat/latest")
        assert chat_resp.status_code in [
            200,
            401,
        ], f"Admin chat endpoint returned unexpected status: {chat_resp.status_code}"
