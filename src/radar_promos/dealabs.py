"""Dealabs : les bons plans de toutes les boutiques, repérés par la communauté."""
import html as htmlmod
import json
import re
import time
from urllib.parse import quote_plus

from . import web

BASE = "https://www.dealabs.com"


def search(query: str) -> list[dict]:
    page = web.get(f"{BASE}/search?q={quote_plus(query)}&sortBy=new")
    if not page:
        return []
    deals = []
    for m in re.finditer(r"data-vue3='([^']*)'", page):
        try:
            d = json.loads(htmlmod.unescape(m.group(1)))
        except ValueError:
            continue
        t = (d.get("props") or {}).get("thread")
        if t and t.get("type") == "Deal" and "price" in t:
            deals.append(t)
    return deals


def image_url(t: dict) -> str:
    img = t.get("mainImage") or {}
    if not img.get("slotId"):
        return ""
    return f"https://static-pepper.dealabs.com/{img['path']}/{img['name']}/re/1024x1024/qt/60/{img['name']}.jpg"


def deal_url(t: dict) -> str:
    return f"{BASE}/bons-plans/{t['titleSlug']}-{t['threadId']}"


def matches(t: dict, item: dict, max_age_h: int = 72) -> bool:
    title = t["title"].lower()
    if t.get("isExpired") or t.get("isLocal") or not t.get("price"):
        return False
    if time.time() - t.get("publishedAt", 0) > max_age_h * 3600:
        return False
    if (t.get("selectedLocations") or {}).get("isNational") is False and re.search(r"\(\d{2}\)", t["title"]):
        return False  # offre limitée à un magasin local
    if not all(w.lower() in title for w in item.get("doit_contenir", [])):
        return False
    if any(w.lower() in title for w in item.get("exclure", [])):
        return False
    if item.get("prix_max") and t["price"] > item["prix_max"]:
        return False
    return True
