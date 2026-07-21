"""HTTP client for external AI APIs (SSL + timeouts for multi-user load)."""
from functools import lru_cache

import httpx

API_TIMEOUT_SEC = 180.0


@lru_cache(maxsize=1)
def get_api_http_client() -> httpx.Client:
    # verify=False: обход CERTIFICATE_VERIFY_FAILED на части ПК
    # limits: при 20 пользователях не открываем бесконечные сокеты
    return httpx.Client(
        verify=False,
        timeout=httpx.Timeout(API_TIMEOUT_SEC, connect=30.0),
        limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
    )
