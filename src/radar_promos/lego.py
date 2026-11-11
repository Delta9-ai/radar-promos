"""Lego : Avenue de la Brique (prix par boutique) + Brickfact (valeur de revente, retraite)."""
import html as htmlmod
import re
from dataclasses import dataclass, field

from selectolax.lexbor import LexborHTMLParser as HTMLParser

from . import web

ADB = "https://www.avenuedelabrique.com"


@dataclass
class LegoSet:
    set_id: str
    name: str
    url: str
    best_price: float
    reduc: int  # % affiché par Avenue de la Brique (vs prix LEGO)
    image: str = ""
    rrp: float | None = None  # prix conseillé LEGO
    offers: list[dict] = field(default_factory=list)  # [{shop, price, link, seen}]
    market_value: float | None = None  # valeur de revente (Brickfact)
    retiring: bool = False


def _price(txt: str) -> float | None:
    m = re.search(r"(\d+(?:[.,]\d{1,2})?)", txt.replace("\xa0", ""))
    return float(m.group(1).replace(",", ".")) if m else None


def list_star_wars() -> list[LegoSet]:
    """Une seule page = tous les Lego Star Wars avec leur meilleur prix actuel."""
    page = web.get(f"{ADB}/tous-les-lego-star-wars/c29")
    if not page:
        return []
    out = []
    for li in HTMLParser(page).css("li.lprod"):
        a = li.css_first("a")
        prix = li.css_first(".lprod-prix span")
        if not a or not prix:
            continue  # set plus vendu
        url = a.attributes.get("href", "")
        m = re.search(r"/(\d{4,6})-", url)
        if not m:
            continue
        price = _price(prix.text())
        if not price:
            continue
        reduc_el = li.css_first(".lprod-reduc")
        reduc = int(re.sub(r"\D", "", reduc_el.text()) or 0) if reduc_el else 0
        lib = li.css_first(".lprod-lib")
        if lib:
            for em in lib.css("em"):  # nom anglais en double
                em.decompose()
        name = lib.text(separator=" ", strip=True) if lib else m.group(1)
        name = re.sub(r"\s+", " ", name).strip()
        img = li.css_first("img")
        image = img.attributes.get("data-src", "") if img else ""
        out.append(
            LegoSet(m.group(1), name, url, price, reduc, image=ADB + image.replace("_0x80", "") if image else "")
        )
    return out


def enrich_offers(s: LegoSet) -> None:
    """Page produit : prix chez chaque boutique + prix conseillé LEGO + belle image."""
    page = web.get(s.url)
    if not page:
        return
    tree = HTMLParser(page)
    for px in tree.css(".prodf-comp-px .prodf-px"):
        img = px.css_first("img")
        alt = img.attributes.get("alt", "") if img else ""
        shop = alt.split(" chez ")[-1].strip() if " chez " in alt else "?"
        price = _price(px.attributes.get("data-prix") or "")
        a = px.css_first("a")
        seen = px.css_first(".prodf-px-date span")
        if price:
            s.offers.append(
                {
                    "shop": shop,
                    "price": price,
                    "link": ADB + a.attributes["href"] if a and a.attributes.get("href", "").startswith("/") else s.url,
                    "seen": seen.text(strip=True) if seen else "",
                }
            )
    s.offers.sort(key=lambda o: o["price"])
    # Prix conseillé LEGO : "84.99 € chez LEGO"
    txt = htmlmod.unescape(re.sub(r"<[^>]+>", " ", page))
    m = re.search(r"(\d+[.,]\d{2})\s*€\s*chez LEGO", txt)
    if m:
        s.rrp = float(m.group(1).replace(",", "."))
    og = tree.css_first('meta[property="og:image"]')
    if og and og.attributes.get("content"):
        s.image = og.attributes["content"]


def retiring_ids() -> set[str]:
    """Sets qui partent bientôt à la retraite (Brickfact)."""
    page = web.get("https://brickfact.com/end-of-life")
    return set(re.findall(r"\b(7\d{4})\b", page)) if page else set()


# Brickfact bloque si on lit trop de pages d'affilée : budget limité par passage,
# pause longue, et arrêt immédiat au premier refus.
BRICKFACT_MAX_PAR_PASSAGE = 6
_bf = {"restant": BRICKFACT_MAX_PAR_PASSAGE, "bloque": False}


def brickfact_disponible() -> bool:
    return not _bf["bloque"] and _bf["restant"] > 0


def market_value(set_id: str) -> float | None:
    """Valeur de marché sur le marché secondaire (revente), d'après Brickfact."""
    _bf["restant"] -= 1
    page = web.get(f"https://brickfact.com/fr-fr/sets/{set_id}", pause=(4.0, 7.0))
    if not page:
        if web.last_status in (403, 429):
            _bf["bloque"] = True
            print("  ! Brickfact refuse les lectures : pause jusqu'au prochain passage")
        return None
    txt = htmlmod.unescape(re.sub(r"<[^>]+>", " ", page))
    txt = re.sub(r"\s+", " ", txt)
    m = re.search(r"Valeur marchande actuelle\s*([\d\s]+,\d{2})\s*€", txt)
    return float(m.group(1).replace(" ", "").replace(",", ".")) if m else None
