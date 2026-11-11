"""Hangar99.fr : promos Lego Star Wars Amazon + Fnac, revérifiées plusieurs fois par jour."""
import json
from datetime import datetime, timezone

from . import web

API = "https://www.hangar99.fr/api/promos"


def promos() -> list[dict]:
    """Une offre par (set, boutique) : {set_id, name, image, lego, price, pct, shop, url, at}."""
    page = web.get(API, pause=(0.5, 1.0))
    if not page:
        return []
    try:
        data = json.loads(page)
    except ValueError:
        print("  ! Hangar99 : réponse illisible")
        return []
    out = []
    for shop, key, price_field in (("Amazon", "promos", "amazon"), ("Fnac", "fnac", "price")):
        for p in data.get(key, []):
            price = p.get(price_field)
            if not price or not p.get("lego"):
                continue
            out.append(
                {
                    "set_id": p["setNum"].split("-")[0],
                    "name": p["name"],
                    "image": p.get("imgUrl", ""),
                    "lego": float(p["lego"]),
                    "price": float(price),
                    "pct": p.get("pct", 0),
                    "shop": shop,
                    "url": p.get("url") or f"https://www.hangar99.fr/sets/{p['setNum']}",
                    "at": p.get("at", ""),
                }
            )
    return out


def checked_ago(iso: str) -> str:
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    except ValueError:
        return ""
    mins = int((datetime.now(timezone.utc) - dt).total_seconds() // 60)
    return f"il y a {mins} min" if mins < 60 else f"il y a {mins // 60} h"
