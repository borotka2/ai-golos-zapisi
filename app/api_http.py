"""Shared HTTP client for external AI APIs (fixes SSL issues on some Windows setups)."""
from functools import lru_cache

import httpx

API_TIMEOUT_SEC = 180.0


@lru_cache(maxsize=1)
def get_api_http_client() -> httpx.Client:
    # verify=False: обход CERTIFICATE_VERIFY_FAILED на части ПК с некорректными корневыми сертификатами
    return httpx.Client(verify=False, timeout=API_TIMEOUT_SEC)