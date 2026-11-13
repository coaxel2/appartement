#!/usr/bin/env python3
"""Collecte les annonces T2 et T3 publiées sur les pages publiques de liste de LocService.

Usage : python3 outils/collecte_locservice.py sortie.json

Lit les pages de liste par commune (une requête par page, avec une pause),
garde les annonces dans la tolérance de loyer et de surface, puis ouvre chaque
fiche retenue pour lire la description complète (extérieur, parking, photos).
Le résultat est au format attendu par `annonces.py ajouter`.
"""
import html
import json
import re
import sys
import time
import urllib.request
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
CRITERES = json.loads((RACINE / "config" / "criteres.json").read_text(encoding="utf-8"))
COMMUNES = ["bordeaux", "le-bouscat", "bruges", "talence", "merignac", "begles", "eysines",
            "cenon", "lormont", "floirac", "blanquefort", "pessac"]
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"


def lire(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "fr-FR"})
    with urllib.request.urlopen(req, timeout=30) as r:
        final = r.geturl()
        return final, r.read().decode("utf-8", "ignore")


def texte(fragment):
    fragment = re.sub(r"<script.*?</script>|<style.*?</style>", " ", fragment, flags=re.S)
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", fragment))).strip()


def cartes(page):
    for bloc in re.findall(r'<li class="accommodation-ad".*?</li>\s*(?=<li class="accommodation-ad"|</ul>)', page, re.S):
        lien = re.search(r'href="(https://www\.locservice\.fr/[^"]+)"[^>]*>([^<]+)</a>', bloc)
        if not lien:
            continue
        caracs = [texte(c) for c in re.findall(r'<li class="accommodation-ad-characteristic[^"]*">(.*?)</li>', bloc, re.S)]
        desc = re.search(r'<p class="accommodation-ad-description">(.*?)</p>', bloc, re.S)
        img = re.search(r'<img src="([^"]+)"', bloc)
        yield {
            "url": lien.group(1), "titre": html.unescape(lien.group(2)).strip(),
            "caracs": caracs, "extrait": texte(desc.group(1)) if desc else "",
            "photo": img.group(1) if img else None,
        }


def nombre(motif, s):
    m = re.search(motif, s.replace(" ", " ").replace("\xa0", " "))
    return float(m.group(1).replace(" ", "").replace(",", ".")) if m else None


def detecter(desc, mots):
    d = desc.lower()
    for m in mots:
        i = d.find(m)
        if i >= 0:
            avant = d[max(0, i - 25): i]
            if re.search(r"(pas de|sans|aucun|ni)\s+(place de |d'|de )?\S*\s*$", avant):
                return False
            debut = max(desc.rfind(". ", 0, i), desc.rfind("! ", 0, i), i - 70) + 1
            fin = desc.find(". ", i)
            fin = i + 70 if fin < 0 or fin - i > 70 else fin
            return desc[debut:fin].strip(" ,;-")
    return None


def main(sortie):
    vues, resultats = set(), []
    for commune in COMMUNES:
        for t in ("t2", "t3"):
            url = f"https://www.locservice.fr/gironde-33/location-{t}-{commune}.html"
            try:
                _, page = lire(url)
            except Exception as e:  # page absente ou refusée : on passe
                print(f"ignoré {url} : {e}", file=sys.stderr)
                continue
            time.sleep(1.5)
            for c in cartes(page):
                if c["url"] in vues:
                    continue
                vues.add(c["url"])
                lieu = next((x for x in c["caracs"] if re.search(r"\(\d{5}\)", x)), "")
                surface = nombre(r"([\d,]+)\s*m²", " ".join(c["caracs"]))
                loyer = nombre(r"([\d  ]+)\s*€", " ".join(c["caracs"]))
                if "colocation" in c["titre"].lower() or "maison" in c["titre"].lower():
                    continue
                if loyer is None or loyer > CRITERES["tolerance_loyer_cc"]:
                    continue
                if surface is not None and surface < CRITERES["surface_min_m2"]:
                    continue
                cp = re.search(r"\((\d{5})\)", lieu)
                annonce = {
                    "url": c["url"], "site": "LocService", "titre": c["titre"],
                    "loyer_cc": loyer, "surface_m2": surface,
                    "pieces": 3 if "T3" in c["titre"] else 2 if "T2" in c["titre"] else None,
                    "ville": re.sub(r"\s*\(\d{5}\)", "", lieu).strip() or None,
                    "code_postal": cp.group(1) if cp else None,
                    "meuble": "meublé" in c["titre"].lower(),
                    "photos": [c["photo"]] if c["photo"] else [],
                    "description": c["extrait"],
                }
                try:
                    final, fiche = lire(c["url"])
                    time.sleep(1.5)
                    if final.rstrip("/") == c["url"].rstrip("/"):
                        corps = texte(fiche)
                        annonce["description"] = corps[:3000]
                        photos = re.findall(r'(https://img\.locservice\.fr/[^"\s,]+/resize:fit:1280:720/[^"\s,]+\.jpg)', fiche)
                        if photos:
                            annonce["photos"] = list(dict.fromkeys(photos))[:8]
                except Exception as e:
                    print(f"fiche illisible {c['url']} : {e}", file=sys.stderr)
                d = annonce["description"]
                annonce["exterieur"] = detecter(d, ["balcon", "terrasse", "loggia", "jardin"])
                annonce["parking"] = detecter(d, ["parking", "garage", "stationnement", "box"])
                resultats.append(annonce)
    Path(sortie).write_text(json.dumps(resultats, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"{len(resultats)} annonce(s) LocService dans les critères de loyer et surface")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(1)
    main(sys.argv[1])
