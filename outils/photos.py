#!/usr/bin/env python3
"""Complète les photos des annonces et repère celles qui ont été retirées.

Usage : python3 outils/photos.py [--toutes]

Pour chaque annonce active qui a moins de 3 photos (ou toutes avec --toutes),
sur un site lisible (Foncia, LocService, et les autres via og:image), ouvre la
fiche, récupère les photos de l'annonce et les enregistre avec annonces.py.
Une fiche Foncia marquée supprimée ou une fiche LocService qui redirige ailleurs
est marquée expirée. Les sites qui bloquent les robots sont ignorés.
"""
import html
import json
import re
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
BLOQUES = ("seloger.com", "leboncoin.fr", "pap.fr", "logic-immo.com", "ouestfrance-immo.com",
           "avendrealouer.fr", "squarehabitat.fr", "capifrance.fr", "superimmo.com", "trovit.fr")
MAX_PHOTOS = 8


def lire(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "fr-FR"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.geturl(), r.read().decode("utf-8", "ignore")


def uniques(liste):
    return list(dict.fromkeys(u for u in liste if u))[:MAX_PHOTOS]


def foncia(url, page):
    ref = re.search(r"/(\d{6,})\.htm", url)
    texte = page.replace("&q;", '"').replace("&a;", "&")
    photos, expiree = [], False
    if ref:
        i = texte.find(f'"reference":"{ref.group(1)}"')
        if i >= 0:
            # objet JSON qui contient la référence : on remonte à l'accolade ouvrante
            prof, debut = 0, i
            while debut > 0:
                c = texte[debut]
                if c == "}":
                    prof += 1
                elif c == "{":
                    if prof == 0:
                        break
                    prof -= 1
                debut -= 1
            prof, fin = 0, debut
            while fin < len(texte):
                c = texte[fin]
                if c == "{":
                    prof += 1
                elif c == "}":
                    prof -= 1
                    if prof == 0:
                        break
                fin += 1
            bloc = texte[debut:fin + 1]
            photos = re.findall(r"https://storage\.fonciamillenium\.net/thumbnail/[0-9a-f]+/\d+/\d+/\d+", bloc)
            if not photos:
                photos = [u + "/lg.jpeg" for u in re.findall(r"https://[a-z0-9]+\.cloudfront\.net/annonces/[0-9a-f/]+[0-9a-f]", bloc)]
            expiree = '"status":"deleted"' in bloc
    if not photos:
        og = re.search(r'property="og:image" content="([^"]+)"', page)
        photos = [og.group(1)] if og else []
    return uniques(photos), expiree


def locservice(url, final, page):
    if final.rstrip("/") != url.rstrip("/"):
        return [], True
    photos = re.findall(r'(https://img\.locservice\.fr/[^"\s,]+/resize:fit:1280:720/[^"\s,]+\.jpg)', page)
    return uniques(photos), False


def generique(page):
    og = re.findall(r'property="og:image" content="([^"]+)"', page)
    return uniques(og), False


def main(toutes):
    base = json.loads((RACINE / "data" / "annonces.json").read_text(encoding="utf-8"))["annonces"]
    maj, vues = [], 0
    for a in base.values():
        url = a.get("url") or ""
        if a.get("expiree") or any(d in url for d in BLOQUES):
            continue
        if not toutes and len(a.get("photos") or []) >= 3:
            continue
        vues += 1
        try:
            final, page = lire(url)
        except urllib.error.HTTPError as e:
            if e.code in (404, 410):
                maj.append({"url": url, "expiree": True})
                print(f"retirée ({e.code}) : {url}")
            continue
        except Exception as e:
            print(f"illisible : {url} ({e})", file=sys.stderr)
            continue
        time.sleep(1.5)
        if "foncia.com" in url:
            photos, expiree = foncia(url, page)
        elif "locservice.fr" in url:
            photos, expiree = locservice(url, final, page)
        else:
            photos, expiree = generique(page)
        entree = {"url": url}
        if expiree:
            entree["expiree"] = True
            print(f"retirée : {url}")
        if len(photos) > len(a.get("photos") or []):
            entree["photos"] = photos
            print(f"{len(photos)} photo(s) : {url}")
        if len(entree) > 1:
            maj.append(entree)
    if maj:
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as f:
            json.dump(maj, f, ensure_ascii=False)
        subprocess.run([sys.executable, str(RACINE / "outils" / "annonces.py"), "ajouter", f.name], check=True)
    print(f"{vues} fiche(s) ouvertes, {len(maj)} annonce(s) mises à jour")


if __name__ == "__main__":
    main("--toutes" in sys.argv)
