import pytest
from unittest.mock import MagicMock, patch
from core.api_client import APIClient


def test_api_client_initialization():
    client = APIClient(base_url="https://10.1.33.160", verify_ssl=False)
    assert client.base_url == "https://10.1.33.160"
    assert client.is_authenticated is False


@patch("httpx.Client")
def test_api_client_login_success(mock_client_cls):
    mock_session = MagicMock()
    mock_client_cls.return_value = mock_session

    # Step 1: GET /users/login returns HTML with authenticity_token
    get_resp = MagicMock()
    get_resp.status_code = 200
    get_resp.text = '<form><input type="hidden" name="authenticity_token" value="dummy_token_123" /></form>'
    mock_session.get.return_value = get_resp

    # Step 2: POST /users/login redirects to /overview
    post_resp = MagicMock()
    post_resp.status_code = 200
    post_resp.url = "https://10.1.33.160/overview"
    post_resp.text = "<html><body>Welcome Admin</body></html>"
    mock_session.post.return_value = post_resp

    client = APIClient(base_url="https://10.1.33.160", verify_ssl=False)
    success = client.login(username="admin", password="DefaultPassw0rd!")
    assert success is True
    assert client.is_authenticated is True
