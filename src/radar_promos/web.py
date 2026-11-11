"""Téléchargement poli des pages (navigateur classique, petite pause entre requêtes)."""
import random
import time

import httpx

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0 Safari/537.36"
)

_client = httpx.Client(
    headers={"User-Agent": UA, "Accept-Language": "fr-FR,fr;q=0.9"},
    follow_redirects=True,
    timeout=30,
)


def get(url: str, pause: tuple[float, float] = (1.0, 2.5)) -> str | None:
    """Renvoie le HTML de la page, ou None si le site refuse."""
    time.sleep(random.uniform(*pause))
    try:
        r = _client.get(url)
    except httpx.HTTPError as e:
        print(f"  ! réseau {url}: {e}")
        return None
    if r.status_code != 200:
        print(f"  ! {r.status_code} {url}")
        return None
    return r.text
