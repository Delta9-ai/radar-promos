"""Radar Promos : surveille les promos et envoie les bonnes affaires sur Telegram.

Lancer :  uv run radar-promos            (vérifie tout et envoie les alertes)
          uv run radar-promos --test     (affiche seulement, n'envoie rien)
"""
import argparse
import os
import time
from pathlib import Path

import yaml

from . import dealabs, hangar99, lego, store, telegram
from .scoring import DECOTE_REVENTE, evaluate
from .telegram import esc

ROOT = Path(__file__).resolve().parents[2]
EMOJI = {"Consoles": "🎮", "Audio": "🎧", "Photo & vidéo": "📷", "Maison": "🏠", "Lego": "🧱"}


def load_env() -> None:
    env = ROOT / ".env"
    if env.exists():
        for line in env.read_text().splitlines():
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())


def eur(x: float) -> str:
    return f"{x:,.2f} €".replace(",", " ").replace(".", ",")


def verdict_lines(v, approx: bool = False) -> list[str]:
    lines = [f"{v.emoji} <b>{v.label}</b> — note {v.score}/10"]
    if v.margin is not None:
        sign = "+" if v.margin >= 0 else ""
        note = " <i>(estimation grossière)</i>" if approx else ""
        lines.append(f"💰 Marge de revente estimée : <b>{sign}{eur(v.margin)}</b> ({sign}{v.margin_pct:.0f} %){note}")
    lines += [f"• {esc(r)}" for r in v.reasons]
    return lines


# ---------------------------------------------------------------- LEGO STAR WARS
ADB_BEST: dict[str, tuple[float, str, str]] = {}  # set -> (meilleur prix toutes boutiques, url, nom FR)


def get_retiring() -> set[str]:
    old = store.cache.get("brickfact_retraite")
    if old and old["v"] and time.time() - old["ts"] < 24 * 3600:
        return set(old["v"])
    fresh_ids = lego.retiring_ids()
    if fresh_ids:  # ne jamais remplacer la liste par une liste vide (site qui refuse)
        store.cache["brickfact_retraite"] = {"v": sorted(fresh_ids), "ts": int(time.time())}
    return fresh_ids or set(old["v"] if old else [])


def check_hangar99() -> list[dict]:
    """Promos Amazon + Fnac repérées par Hangar99 (dès que le site met à jour ses prix)."""
    print("🛸 Hangar99…")
    offers = hangar99.promos()
    print(f"  {len(offers)} offres")
    retiring = get_retiring()
    by_set: dict[str, list[dict]] = {}
    for o in offers:
        by_set.setdefault(o["set_id"], []).append(o)
    cards = []
    for sid, offs in by_set.items():
        offs.sort(key=lambda o: o["price"])
        o = offs[0]  # la moins chère des deux boutiques
        key = f"lego:{sid}"
        if store.already_sent(key, o["price"]):
            continue
        adb = ADB_BEST.get(sid)
        others = [x["price"] for x in offs[1:]] + ([adb[0]] if adb and adb[0] < o["price"] * 0.999 else [])
        second = min(others) if others else None
        is_retiring = sid in retiring
        v = evaluate(o["price"], o["lego"], resale=store.brickfact_value(sid, lego),
                     lowest_90d=store.lowest_before_today(key), second_best=second, retiring=is_retiring,
                     collector=lego.is_collector(o["name"], o["lego"]))
        saving = o["lego"] - o["price"]
        if v.score < 4.5 and not (saving >= 40 and o["pct"] >= 25):
            continue  # Hangar99 liste déjà des promos : on garde les meilleures (note ou grosse économie)
        if v.score < 5:  # bonne promo, mais pas rentable à revendre tout de suite
            v.emoji, v.label = "🟡", "BONNE PROMO (pour soi ou à garder)"
        name = adb[2] if adb else f"LEGO Star Wars {sid} {o['name']}"
        mv = store.cache.get(f"brickfact_valeur:{sid}", {}).get("v")
        lines = [f"🧱 <b>{esc(name)}</b>", "<i>repéré par Hangar99</i>", "", *verdict_lines(v), "",
                 f"💶 <b>{eur(o['price'])}</b> chez <b>{o['shop']}</b>",
                 f"🏷️ Prix LEGO : <s>{eur(o['lego'])}</s> → <b>-{(1 - o['price'] / o['lego']) * 100:.0f} %</b>"
                 f" ({eur(o['lego'] - o['price'])} d'économie)"]
        if mv:
            lines.append(f"♻️ Valeur de revente actuelle : {eur(mv)} (Brickfact)")
        autres = [f"{x['shop']} {eur(x['price'])}" for x in offs[1:]]
        if adb and adb[0] < o["price"] * 0.999:
            autres.append(f"⚠️ ailleurs dès {eur(adb[0])}")
        if autres:
            lines.append("🏪 Ailleurs : " + " · ".join(autres))
        if o["at"]:
            lines.append(f"🕒 Prix vérifié {hangar99.checked_ago(o['at'])}")
        buttons = [(f"🛒 Acheter chez {o['shop']}", o["url"])]
        if adb:
            buttons.append(("📊 Comparer les prix", adb[1]))
        cards.append({"key": key, "price": o["price"], "score": v.score, "text": "\n".join(lines),
                      "image": o["image"], "buttons": buttons})
    return cards


def check_lego(cfg: dict) -> list[dict]:
    print("🧱 Lego Star Wars (Avenue de la Brique)…")
    sets = lego.list_star_wars()
    print(f"  {len(sets)} sets en vente")
    retiring = get_retiring()
    cards = []
    for s in sets:
        ADB_BEST[s.set_id] = (s.best_price, s.url, s.name)
        key = f"lego:{s.set_id}"
        low90 = store.lowest_before_today(key)
        store.record_price(key, s.best_price)
        s.retiring = s.set_id in retiring
        seuil = cfg["remise_min_retraite"] if s.retiring else cfg["remise_min"]
        if s.reduc < seuil or store.already_sent(key, s.best_price):
            continue
        lego.enrich_offers(s)
        s.market_value = store.brickfact_value(s.set_id, lego)
        price = s.offers[0]["price"] if s.offers else s.best_price
        rrp = s.rrp or round(price / (1 - s.reduc / 100), 2)
        second = s.offers[1]["price"] if len(s.offers) > 1 else None
        v = evaluate(price, rrp, resale=s.market_value, lowest_90d=low90, second_best=second, retiring=s.retiring,
                     collector=lego.is_collector(s.name, rrp))
        if v.score < 5:
            continue  # remise affichée mais pas une vraie bonne affaire

        best = s.offers[0] if s.offers else {"shop": "?", "link": s.url, "seen": ""}
        lines = [
            f"🧱 <b>{esc(s.name)}</b>",
            "",
            *verdict_lines(v),
            "",
            f"💶 <b>{eur(price)}</b> chez <b>{esc(best['shop'])}</b>",
            f"🏷️ Prix LEGO : <s>{eur(rrp)}</s> → <b>-{(1 - price / rrp) * 100:.0f} %</b>",
        ]
        if s.market_value:
            lines.append(f"♻️ Valeur de revente actuelle : {eur(s.market_value)} (Brickfact)")
        if len(s.offers) > 1:
            autres = " · ".join(f"{esc(o['shop'])} {eur(o['price'])}" for o in s.offers[1:5])
            lines.append(f"🏪 Ailleurs : {autres}")
        if best.get("seen"):
            lines.append(f"🕒 Prix vu le {esc(best['seen'])}")
        cards.append(
            {
                "key": key,
                "price": price,
                "score": v.score,
                "text": "\n".join(lines),
                "image": s.image,
                "buttons": [(f"🛒 Acheter chez {best['shop']}", best["link"]), ("📊 Comparer les prix", s.url)],
            }
        )
    return cards


# ---------------------------------------------------------------- DEALABS (tout le reste)
def deal_card(t: dict, item: dict) -> dict | None:
    perso = item.get("mode") == "perso"
    price, ref = float(t["price"]), float(t.get("nextBestPrice") or 0) or None
    key = f"deal:{t['threadId']}"
    if store.already_sent(key, price):
        return None
    hist_key = f"prix:{item['nom']}"
    low90 = store.lowest_before_today(hist_key)
    store.record_price(hist_key, price)
    resale = ref * DECOTE_REVENTE if ref else None
    v = evaluate(price, ref, resale=resale, lowest_90d=low90, temperature=t.get("temperature"), perso=perso)
    if not perso and v.score < 5:
        return None
    if perso and not ref and (t.get("temperature") or 0) < 50:
        return None  # pas de vraie réduction visible
    shop_key = f"offre:{item['nom']}:{(t.get('merchant') or {}).get('merchantName')}:{price}"
    if store.already_sent(shop_key, price):
        return None  # même offre déjà postée plusieurs fois sur Dealabs

    shop = (t.get("merchant") or {}).get("merchantName") or t.get("linkHost") or "?"
    emoji = EMOJI.get(item.get("categorie"), "🛍️")
    tag = "  <i>(pour toi)</i>" if perso else ""
    lines = [f"{emoji} <b>{esc(t['title'])}</b>{tag}", "", *verdict_lines(v, approx=True), "",
             f"💶 <b>{eur(price)}</b> chez <b>{esc(shop)}</b>"]
    if ref:
        lines.append(f"🏷️ Prix habituel ailleurs : <s>{eur(ref)}</s> → <b>-{(1 - price / ref) * 100:.0f} %</b>")
    ship = t.get("shipping") or {}
    if ship.get("isFree"):
        lines.append("🚚 Livraison gratuite")
    elif ship.get("price"):
        lines.append(f"🚚 Livraison : {eur(ship['price'])}")
    if t.get("voucherCode") and not t.get("isVoucherCodeHidden"):
        lines.append(f"🎟️ Code promo : <code>{esc(t['voucherCode'])}</code>")
    return {
        "key": key,
        "keys": [key, shop_key],
        "price": price,
        "score": v.score + (3 if perso else 0),  # les consoles pour toi passent en priorité
        "text": "\n".join(lines),
        "image": dealabs.image_url(t),
        "buttons": [("🛒 Voir l'offre", f"https://www.dealabs.com/visit/thread/{t['threadId']}"),
                    ("💬 Détails sur Dealabs", dealabs.deal_url(t))],
    }


def check_dealabs(items: list[dict], cfg_lego: dict) -> list[dict]:
    print("🔎 Dealabs…")
    cards, seen = [], set()
    for item in items:
        for t in dealabs.search(item["search"]):
            if t["threadId"] in seen or not dealabs.matches(t, item):
                continue
            seen.add(t["threadId"])
            c = deal_card(t, item)
            if c:
                cards.append(c)
                print(f"  + {item['nom']}: {t['title'][:70]} ({t['price']} €)")
    # Les autres Lego (hors Star Wars), seulement s'ils cartonnent sur Dealabs
    autre = {"nom": "Lego (autres)", "categorie": "Lego", "mode": "revente",
             "doit_contenir": ["lego"], "exclure": ["star wars", "reconditionn", "occasion", "compatible"]}
    for t in dealabs.search("lego"):
        if t["threadId"] in seen or not dealabs.matches(t, autre):
            continue
        if (t.get("temperature") or 0) < cfg_lego.get("autres_lego_temperature_min", 150):
            continue
        c = deal_card(t, autre)
        if c:
            cards.append(c)
    return cards


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--test", action="store_true", help="affiche les fiches sans les envoyer")
    ap.add_argument("--max", type=int, default=8, help="nombre max de fiches envoyées par passage")
    args = ap.parse_args()
    load_env()
    cfg = yaml.safe_load((ROOT / "watchlist.yaml").read_text())

    cards = []
    if cfg["lego"].get("star_wars_tous"):
        cards += check_lego(cfg["lego"])
    if cfg["lego"].get("hangar99", True):
        cards += check_hangar99()
    cards += check_dealabs(cfg.get("produits", []), cfg["lego"])
    cards.sort(key=lambda c: -c["score"])
    uniq, vus = [], set()
    for c in cards:
        k = c.get("keys", [c["key"]])[-1]
        if k not in vus:
            vus.add(k)
            uniq.append(c)
    cards = uniq
    print(f"\n{len(cards)} bonne(s) affaire(s) trouvée(s), envoi des {min(len(cards), args.max)} meilleures")

    for c in cards[: args.max]:
        if args.test:
            print("\n" + "-" * 60 + "\n" + c["text"] + f"\n[image] {c['image']}\n[boutons] {c['buttons']}")
        elif telegram.send_card(c["text"], c["image"], c["buttons"]):
            for k in c.get("keys", [c["key"]]):
                store.mark_sent(k, c["price"])
    if not args.test:
        store.save_all()
