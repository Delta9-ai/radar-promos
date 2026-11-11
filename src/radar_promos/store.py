"""Mémoire de l'outil : historique des prix + alertes déjà envoyées (fichiers JSON dans data/)."""
import json
import time
from pathlib import Path

DATA = Path(__file__).resolve().parents[2] / "data"
DATA.mkdir(exist_ok=True)


def _load(name: str) -> dict:
    p = DATA / name
    return json.loads(p.read_text()) if p.exists() else {}


def _save(name: str, d: dict) -> None:
    (DATA / name).write_text(json.dumps(d, ensure_ascii=False, indent=1, sort_keys=True))


history = _load("historique_prix.json")  # clé -> {jour: prix mini}
sent = _load("alertes_envoyees.json")  # clé -> {prix, ts}
cache = _load("cache.json")  # clé -> {v, ts}


def record_price(key: str, price: float) -> None:
    day = time.strftime("%Y-%m-%d")
    h = history.setdefault(key, {})
    h[day] = min(price, h.get(day, price))


def lowest_before_today(key: str, days: int = 90) -> float | None:
    today = time.strftime("%Y-%m-%d")
    cutoff = time.strftime("%Y-%m-%d", time.localtime(time.time() - days * 86400))
    vals = [p for d, p in history.get(key, {}).items() if cutoff <= d < today]
    return min(vals) if vals else None


def already_sent(key: str, price: float) -> bool:
    """Déjà alerté à ce prix (ou moins cher) dans les 3 derniers jours ?"""
    s = sent.get(key)
    return bool(s and price >= s["prix"] * 0.98 and time.time() - s["ts"] < 3 * 86400)


def mark_sent(key: str, price: float) -> None:
    sent[key] = {"prix": price, "ts": int(time.time())}


def cached(key: str, max_age_h: float, fn):
    c = cache.get(key)
    if c and time.time() - c["ts"] < max_age_h * 3600:
        return c["v"]
    v = fn()
    cache[key] = {"v": v, "ts": int(time.time())}
    return v


def save_all() -> None:
    _save("historique_prix.json", history)
    _save("alertes_envoyees.json", sent)
    _save("cache.json", cache)
