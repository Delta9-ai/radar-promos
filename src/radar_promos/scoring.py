"""La note « ça vaut le coup ? » sur 10, et le détail qui l'explique."""
from dataclasses import dataclass, field

# Hypothèses de revente (Leboncoin / Vinted, produit neuf sous blister)
DECOTE_REVENTE = 0.70  # prudence : un produit neuf se revend ~70 % du prix habituel affiché
FRAIS_REVENTE = 0.05  # frais divers (envoi, protection, commission)


@dataclass
class Verdict:
    score: float
    emoji: str
    label: str
    reasons: list[str] = field(default_factory=list)
    margin: float | None = None
    margin_pct: float | None = None


def evaluate(
    price: float,
    ref_price: float | None,
    *,
    resale: float | None = None,
    lowest_90d: float | None = None,
    second_best: float | None = None,
    retiring: bool = False,
    temperature: float | None = None,
    perso: bool = False,
) -> Verdict:
    pts, why = 0.0, []

    # 1) Remise réelle par rapport au prix de référence (max 4 pts)
    disc = (1 - price / ref_price) * 100 if ref_price and ref_price > price else 0
    pts += min(4.0, disc / 10)
    if disc:
        why.append(f"-{disc:.0f} % vs prix habituel")

    # 2) Historique : est-ce le plus bas des 90 derniers jours ? (+1,5 / -2)
    if lowest_90d:
        if price <= lowest_90d * 1.01:
            pts += 1.5
            why.append("plus bas prix des 3 derniers mois")
        elif price > lowest_90d * 1.10:
            pts -= 2
            why.append(f"⚠️ déjà vu à {lowest_90d:.2f} € récemment")

    # 3) Comparaison avec les autres sites (+1)
    if second_best and second_best > price * 1.05:
        pts += 1
        why.append(f"{(1 - price / second_best) * 100:.0f} % moins cher que le 2e site")

    # 4) Marge de revente (max 3 pts)
    margin = margin_pct = None
    if resale and not perso:
        margin = resale * (1 - FRAIS_REVENTE) - price
        margin_pct = margin / price * 100
        # une petite marge en euros compte moins (5 € de marge sur 10 € = peu d'intérêt)
        pts += max(0.0, min(3.0, margin_pct / 10)) * max(0.0, min(1.0, margin / 25))
        if margin < 5:
            pts -= 1

    # 5) Set qui part à la retraite (+1,5)
    if retiring:
        pts += 1.5
        why.append("🔚 part bientôt à la retraite (prix de revente qui monte ensuite)")

    # 6) Avis de la communauté Dealabs (+0,5 à +1,5)
    if temperature is not None:
        if temperature >= 300:
            pts += 1.5
            why.append(f"🔥 {temperature:.0f}° sur Dealabs (énorme succès)")
        elif temperature >= 100:
            pts += 1
            why.append(f"🔥 {temperature:.0f}° sur Dealabs")
        elif temperature >= 40:
            pts += 0.5
        elif temperature < 0:
            pts -= 1.5
            why.append(f"🧊 {temperature:.0f}° sur Dealabs (la communauté n'aime pas)")

    score = max(0.0, min(10.0, pts))
    if score >= 7:
        emoji, label = "✅", "FONCE"
    elif score >= 5:
        emoji, label = "⚠️", "À VOIR"
    else:
        emoji, label = "❌", "BOF"
    return Verdict(round(score, 1), emoji, label, why, margin, margin_pct)
