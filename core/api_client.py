import re
from typing import Optional
import httpx
from bs4 import BeautifulSoup
from config.settings import settings


class APIClient:
    def __init__(
        self,
        base_url: str,
        verify_ssl: bool = False,
        timeout: float = 15.0,
    ):
        self.base_url = base_url.rstrip("/")
        self.verify_ssl = verify_ssl
        self.timeout = timeout
        self.session = httpx.Client(
            verify=verify_ssl,
            timeout=timeout,
            follow_redirects=True,
            headers={
                "User-Agent": "Redborder-Tester/0.1.0",
                "Accept": "text/html,application/xhtml+xml,application/json,*/*",
            },
        )
        self.csrf_token: Optional[str] = None
        self.is_authenticated: bool = False

    def close(self) -> None:
        self.session.close()

    def __enter__(self) -> "APIClient":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()

    def fetch_csrf_token(self) -> Optional[str]:
        response = self.session.get(f"{self.base_url}/users/login")
        if response.status_code >= 400:
            return None

        soup = BeautifulSoup(response.text, "html.parser")

        # Try input name="authenticity_token"
        token_input = soup.find("input", {"name": "authenticity_token"})
        if token_input and token_input.get("value"):
            self.csrf_token = token_input["value"]
            return self.csrf_token

        # Try meta name="csrf-token"
        meta_token = soup.find("meta", {"name": "csrf-token"})
        if meta_token and meta_token.get("content"):
            self.csrf_token = meta_token["content"]
            return self.csrf_token

        # Regex fallback
        match = re.search(r'name="authenticity_token"\s+value="([^"]+)"', response.text)
        if match:
            self.csrf_token = match.group(1)
            return self.csrf_token

        return None

    def login(
        self,
        username: Optional[str] = None,
        password: Optional[str] = None,
        auth_method: str = "database",
    ) -> bool:
        user = username if username is not None else settings.web_user
        pwd = password if password is not None else settings.web_password

        csrf = self.fetch_csrf_token()
        payload = {
            "utf8": "✓",
            "authenticity_token": csrf or "",
            "user[username]": user,
            "user[password]": pwd,
            "user[remember_me]": "1",
            "auth_method": auth_method,
        }

        response = self.session.post(
            f"{self.base_url}/users/login",
            data=payload,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )

        final_url_str = str(response.url)
        has_auth_error = any(
            err in response.text
            for err in [
                "Invalid Username or password",
                "Invalid email or password",
                "Invalid credentials",
            ]
        )

        if (
            response.status_code == 200
            and "login" not in final_url_str
            and not has_auth_error
        ):
            self.is_authenticated = True
            # Extract refreshed CSRF token from authenticated session
            soup = BeautifulSoup(response.text, "html.parser")
            meta_token = soup.find("meta", {"name": "csrf-token"})
            if meta_token and meta_token.get("content"):
                self.csrf_token = meta_token["content"]
            return True

        self.is_authenticated = False
        return False

    def get(self, endpoint: str, **kwargs) -> httpx.Response:
        url = endpoint if endpoint.startswith("http") else f"{self.base_url}/{endpoint.lstrip('/')}"
        return self.session.get(url, **kwargs)

    def post(self, endpoint: str, **kwargs) -> httpx.Response:
        url = endpoint if endpoint.startswith("http") else f"{self.base_url}/{endpoint.lstrip('/')}"
        headers = dict(kwargs.pop("headers", None) or {})
        if self.csrf_token and "X-CSRF-Token" not in headers:
            headers["X-CSRF-Token"] = self.csrf_token
        return self.session.post(url, headers=headers, **kwargs)

    def delete(self, endpoint: str, **kwargs) -> httpx.Response:
        url = endpoint if endpoint.startswith("http") else f"{self.base_url}/{endpoint.lstrip('/')}"
        headers = dict(kwargs.pop("headers", None) or {})
        if self.csrf_token and "X-CSRF-Token" not in headers:
            headers["X-CSRF-Token"] = self.csrf_token
        return self.session.delete(url, headers=headers, **kwargs)
