#!/usr/bin/env python3
"""Gestion des annonces : fusion, dédoublonnage, évaluation et rapport.

Usage :
  python3 outils/annonces.py ajouter nouvelles.json   # fusionne des annonces trouvées
  python3 outils/annonces.py rapport                  # écrit les rapports et site/donnees.json
  python3 outils/annonces.py stats                    # résumé rapide

Format d'une annonce (champs inconnus = null) :
{
  "url": "https://...", "site": "PAP", "titre": "T2 avec balcon",
  "loyer_cc": 690, "loyer_hc": 640, "charges": 50, "parking_supplement": 0,
  "surface_m2": 42, "pieces": 2, "ville": "Le Bouscat", "code_postal": "33110",
  "quartier": "Ermitage", "exterieur": "balcon 6 m²", "parking": "place en sous-sol",
  "meuble": false, "disponible": "2026-12-01", "publie_le": "2026-11-12",
  "photos": ["https://..."], "description": "...", "contact": "agence X"
}
"""
import datetime as dt
import hashlib
import json
import re
import sys
import unicodedata
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
DONNEES = RACINE / "data" / "annonces.json"
CRITERES = json.loads((RACINE / "config" / "criteres.json").read_text(encoding="utf-8"))
ZONES = json.loads((RACINE / "config" / "zones.json").read_text(encoding="utf-8"))["zones"]


def normaliser(texte):
    texte = unicodedata.normalize("NFKD", texte or "").encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", " ", texte.lower()).strip()


def identifiant(a):
    url = re.sub(r"[?#].*$", "", (a.get("url") or "").strip().rstrip("/"))
    return hashlib.sha1(url.encode()).hexdigest()[:12]


def empreinte(a):
    """Repère la même annonce publiée sur plusieurs sites."""
    return "|".join(str(x) for x in (
        normaliser(a.get("ville")), a.get("pieces"),
        round(float(a.get("surface_m2") or 0)), round(float(a.get("loyer_cc") or 0) / 10),
    ))


def zone_de(a):
    texte = normaliser(" ".join(str(a.get(k) or "") for k in ("ville", "quartier", "titre")))
    cp = str(a.get("code_postal") or "")
    meilleure = None
    for z in ZONES:
        mots = [m for m in normaliser(z["nom"]).split() if len(m) > 3 and m not in ("bordeaux", "proche", "tram", "centre")]
        if any(m in texte for m in mots):
            if meilleure is None or z["minutes"] < meilleure["minutes"]:
                meilleure = z
    if meilleure is None and cp:
        candidates = [z for z in ZONES if cp in z["codes_postaux"]]
        if candidates:
            meilleure = max(candidates, key=lambda z: z["minutes"])
    return meilleure


def evaluer(a):
    c = CRITERES
    raisons, manques = [], []
    loyer = a.get("loyer_cc")
    if loyer is None and a.get("loyer_hc") is not None:
        loyer = a["loyer_hc"] + (a.get("charges") or 0)
    if loyer is not None:
        loyer += a.get("parking_supplement") or 0
    a["loyer_total"] = loyer

    if loyer is None:
        manques.append("loyer inconnu")
    elif loyer > c["tolerance_loyer_cc"]:
        raisons.append(f"loyer {loyer} € > {c['tolerance_loyer_cc']} €")
    elif loyer > c["loyer_max_cc"]:
        manques.append(f"loyer {loyer} € légèrement au dessus de {c['loyer_max_cc']} €")

    p = a.get("pieces")
    if p is None:
        manques.append("nombre de pièces inconnu")
    elif not c["pieces_min"] <= p <= c["pieces_max"]:
        raisons.append(f"{p} pièce(s)")

    s = a.get("surface_m2")
    if s is None:
        manques.append("surface inconnue")
    elif s < c["surface_min_m2"]:
        raisons.append(f"{s} m² < {c['surface_min_m2']} m²")

    for champ, libelle in (("exterieur", "extérieur"), ("parking", "parking")):
        v = a.get(champ)
        if v in (None, "", "inconnu"):
            manques.append(f"{libelle} non précisé")
        elif v is False or normaliser(str(v)) in ("non", "aucun", "false"):
            manques.append(f"sans {libelle}")

    notes = []
    z = zone_de(a)
    a["zone"] = z["nom"] if z else None
    a["trajet_estime_min"] = a.get("trajet_verifie_min") or (z["minutes"] if z else None)
    cps_connus = {cp for zone in ZONES for cp in zone["codes_postaux"]}
    if a.get("trajet_verifie_min"):
        if a["trajet_verifie_min"] > c["trajet_max_minutes"]:
            raisons.append(f"trajet vérifié {a['trajet_verifie_min']} min")
    elif z is None and a.get("code_postal") and str(a["code_postal"]) not in cps_connus:
        raisons.append("commune hors zone de trajet")
    elif z is None:
        manques.append("trajet à vérifier")
    elif z["minutes"] > c["trajet_max_minutes"]:
        raisons.append(f"trajet estimé {z['minutes']} min")
    elif z["statut"] == "limite":
        notes.append(f"trajet estimé ~{z['minutes']} min, à confirmer")

    if raisons:
        statut = "rejetee"
    elif not manques:
        statut = "correspond"
    elif len(manques) == 1:
        statut = "a_verifier"
    else:
        statut = "incomplete"
    a["statut"], a["raisons_rejet"], a["points_a_verifier"] = statut, raisons, manques + notes
    return a


def charger():
    if DONNEES.exists():
        return json.loads(DONNEES.read_text(encoding="utf-8"))
    return {"annonces": {}}


def sauver(base):
    DONNEES.parent.mkdir(exist_ok=True)
    DONNEES.write_text(json.dumps(base, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def ajouter(chemin):
    nouvelles = json.loads(Path(chemin).read_text(encoding="utf-8"))
    if isinstance(nouvelles, dict):
        nouvelles = nouvelles.get("annonces", [nouvelles])
    base = charger()
    maintenant = dt.datetime.now().isoformat(timespec="minutes")
    empreintes = {empreinte(v): k for k, v in base["annonces"].items() if v.get("loyer_cc") and v.get("surface_m2")}
    ajoutees = maj = doublons = 0
    for a in nouvelles:
        if not a.get("url"):
            continue
        cle = identifiant(a)
        e = empreinte(a)
        if cle not in base["annonces"] and a.get("loyer_cc") and a.get("surface_m2") and e in empreintes:
            orig = base["annonces"][empreintes[e]]
            autres = set(orig.get("autres_urls", [])) | {a["url"]}
            orig["autres_urls"] = sorted(autres - {orig["url"]})
            doublons += 1
            continue
        if cle in base["annonces"]:
            ancien = base["annonces"][cle]
            for k, v in a.items():
                if v not in (None, "", []):
                    ancien[k] = v
            ancien["vue_le"] = maintenant
            evaluer(ancien)
            maj += 1
        else:
            a["trouvee_le"] = a["vue_le"] = maintenant
            base["annonces"][cle] = evaluer(a)
            ajoutees += 1
    sauver(base)
    print(f"{ajoutees} nouvelle(s), {maj} mise(s) à jour, {doublons} doublon(s) inter sites")


def bloc(a, nouveau):
    lignes = []
    titre = a.get("titre") or "Annonce"
    marque = " (nouvelle)" if nouveau else ""
    lignes.append(f"### {titre}{marque}\n")
    for photo in (a.get("photos") or [])[:4]:
        lignes.append(f"![photo]({photo})")
    if a.get("photos"):
        lignes.append("")
    def f(v, suffixe=""):
        if isinstance(v, float) and v.is_integer():
            v = int(v)
        return "?" if v in (None, "") else f"{v}{suffixe}"
    lignes += [
        f"- Loyer total : **{f(a.get('loyer_total'), ' €')}** (CC, parking inclus si en supplément)",
        f"- Surface : {f(a.get('surface_m2'), ' m²')}, {f(a.get('pieces'))} pièce(s)",
        f"- Localisation : {f(a.get('ville'))} {a.get('code_postal') or ''} {('(' + a['quartier'] + ')') if a.get('quartier') else ''}".rstrip(),
        f"- Trajet estimé : {f(a.get('trajet_estime_min'), ' min')} ({a.get('zone') or 'zone inconnue'})",
        f"- Extérieur : {f(a.get('exterieur'))}",
        f"- Parking : {f(a.get('parking'))}",
        f"- Disponible : {f(a.get('disponible'))}, publiée le {f(a.get('publie_le'))}",
    ]
    if a.get("points_a_verifier"):
        lignes.append(f"- A vérifier : {', '.join(a['points_a_verifier'])}")
    lignes.append(f"- Source : [{a.get('site') or 'annonce'}]({a['url']})")
    for u in a.get("autres_urls", []):
        lignes.append(f"- Aussi publiée ici : [{u.split('/')[2]}]({u})")
    lignes.append("")
    return "\n".join(lignes)


def rapport():
    base = charger()
    for a in base["annonces"].values():
        evaluer(a)
    sauver(base)
    aujourd = dt.date.today().isoformat()
    annonces = list(base["annonces"].values())
    actives = [a for a in annonces if not a.get("expiree")]
    def tri(a):
        return (a.get("loyer_total") or 9999, -(a.get("surface_m2") or 0))
    sections = [
        ("Annonces qui cochent tous les critères", "correspond"),
        ("Annonces à vérifier (un seul point incertain)", "a_verifier"),
        ("Annonces incomplètes (plusieurs informations manquantes)", "incomplete"),
    ]
    c = CRITERES
    lignes = [
        f"# Rapport de recherche du {aujourd}\n",
        "## Critères\n",
        f"- Location, loyer charges comprises max {c['loyer_max_cc']} € (tolérance {c['tolerance_loyer_cc']} €)",
        f"- T{c['pieces_min']} ou T{c['pieces_max']}, {c['surface_min_m2']} m² minimum",
        "- Extérieur (balcon, terrasse, jardin) et parking",
        f"- Max {c['trajet_max_minutes']} min en transports vers le quai des Chartrons et la rue de Turenne\n",
    ]
    for titre, statut in sections:
        liste = sorted([a for a in actives if a.get("statut") == statut], key=tri)
        lignes.append(f"## {titre} ({len(liste)})\n")
        if not liste:
            lignes.append("Aucune pour le moment.\n")
        for a in liste:
            lignes.append(bloc(a, (a.get("trouvee_le") or "").startswith(aujourd)))
    rejetees = [a for a in actives if a.get("statut") == "rejetee"]
    lignes.append(f"## Annonces écartées ({len(rejetees)})\n")
    for a in sorted(rejetees, key=tri):
        lignes.append(f"- [{a.get('titre') or a['url']}]({a['url']}) : {', '.join(a['raisons_rejet'])}")
    lignes.append("")
    texte = "\n".join(lignes)
    (RACINE / "rapports").mkdir(exist_ok=True)
    (RACINE / "rapports" / f"{aujourd}.md").write_text(texte, encoding="utf-8")
    (RACINE / "rapports" / "DERNIER.md").write_text(texte, encoding="utf-8")
    export_site()
    stats()


def export_site():
    """Ecrit site/donnees.json, lu par le site web (déployé sur Vercel)."""
    base = charger()["annonces"]
    sites = json.loads((RACINE / "config" / "sites.json").read_text(encoding="utf-8"))
    compte = {}
    annonces = []
    for cle, a in base.items():
        compte[a.get("statut")] = compte.get(a.get("statut"), 0) + 1
        d = {k: a.get(k) for k in (
            "titre", "site", "url", "autres_urls", "loyer_total", "loyer_cc", "charges", "surface_m2", "pieces",
            "ville", "code_postal", "quartier", "zone", "trajet_estime_min", "trajet_verifie_min", "exterieur",
            "parking", "meuble", "disponible", "publie_le", "statut", "raisons_rejet", "points_a_verifier",
            "trouvee_le", "vue_le", "expiree", "contact")}
        d["id"] = cle
        d["photos_urls"] = [] if a.get("statut") == "rejetee" else (a.get("photos") or [])[:6]
        d["description"] = (a.get("description") or "")[:700]
        annonces.append(d)
    donnees = {
        "config": {
            "criteres": CRITERES, "zones": ZONES, "sites": sites.get("sites", []), "villes": sites.get("villes", []),
            "stats": {"total": len(base), "par_statut": compte},
            "mise_a_jour": dt.datetime.now().isoformat(timespec="minutes"),
        },
        "annonces": annonces,
    }
    (RACINE / "site").mkdir(exist_ok=True)
    (RACINE / "site" / "donnees.json").write_text(json.dumps(donnees, ensure_ascii=False, indent=1), encoding="utf-8")


def stats():
    base = charger()
    compte = {}
    aujourd = dt.date.today().isoformat()
    nouvelles = 0
    for a in base["annonces"].values():
        compte[a.get("statut")] = compte.get(a.get("statut"), 0) + 1
        if (a.get("trouvee_le") or "").startswith(aujourd) and a.get("statut") in ("correspond", "a_verifier"):
            nouvelles += 1
    print(json.dumps({"total": len(base["annonces"]), "par_statut": compte, "nouvelles_pertinentes_aujourdhui": nouvelles}, ensure_ascii=False))


if __name__ == "__main__":
    commande = sys.argv[1] if len(sys.argv) > 1 else "stats"
    if commande == "ajouter" and len(sys.argv) == 3:
        ajouter(sys.argv[2])
    elif commande == "rapport":
        rapport()
    elif commande == "stats":
        stats()
    else:
        print(__doc__)
        sys.exit(1)
