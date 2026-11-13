#!/usr/bin/env python3
"""Publie l'avancement de la recherche automatique, affiché en direct sur le site.

Usage :
  python3 outils/statut.py debut
  python3 outils/statut.py etape "Recherche web : T2 balcon parking à Talence (12 / 25)" [--detail "SeLoger, PAP"]
  python3 outils/statut.py fin [--resume "3 nouvelles annonces qui correspondent"]
  python3 outils/statut.py erreur "message"

Chaque appel met à jour site/statut.json puis le committe et le pousse aussitôt
(sauf avec --sans-push). Le site lit ce fichier sur GitHub toutes les 30 secondes
pendant une recherche.
"""
import datetime as dt
import json
import subprocess
import sys
import time
from pathlib import Path
from zoneinfo import ZoneInfo

RACINE = Path(__file__).resolve().parent.parent
FICHIER = RACINE / "site" / "statut.json"
PARIS = ZoneInfo("Europe/Paris")
HORAIRES = ["08:17", "11:17", "15:17", "19:17"]
BRANCHE = "claude/wizardly-babbage-v4rr4a"
MAX_ETAPES = 40


def maintenant():
    return dt.datetime.now(PARIS).isoformat(timespec="seconds")


def lire():
    try:
        return json.loads(FICHIER.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def ecrire(etat, message, pousser):
    etat["horaires"] = HORAIRES
    etat["fuseau"] = "Europe/Paris"
    etat["maj"] = maintenant()
    FICHIER.parent.mkdir(exist_ok=True)
    FICHIER.write_text(json.dumps(etat, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    if not pousser:
        return
    try:
        subprocess.run(["git", "add", str(FICHIER)], cwd=RACINE, check=True)
        r = subprocess.run(["git", "commit", "-q", "-m", f"Statut : {message}"[:120]], cwd=RACINE)
        if r.returncode != 0:
            return
        for essai in range(4):
            if subprocess.run(["git", "push", "-q", "origin", f"HEAD:{BRANCHE}"], cwd=RACINE).returncode == 0:
                return
            subprocess.run(["git", "pull", "-q", "--rebase", "origin", BRANCHE], cwd=RACINE)
            time.sleep(2 ** (essai + 1))
        print("push du statut impossible, la recherche continue", file=sys.stderr)
    except Exception as e:  # le statut ne doit jamais bloquer la recherche
        print(f"statut non publié : {e}", file=sys.stderr)


def main(args):
    pousser = "--sans-push" in args
    pousser = not pousser
    args = [a for a in args if a != "--sans-push"]

    def option(nom):
        if nom in args:
            i = args.index(nom)
            valeur = args[i + 1] if i + 1 < len(args) else ""
            del args[i:i + 2]
            return valeur
        return None

    detail = option("--detail")
    resume = option("--resume")
    if not args:
        print(__doc__)
        sys.exit(1)
    commande = args[0]
    etat = lire()

    if commande == "debut":
        etat.update({"en_cours": True, "debut": maintenant(), "fin": None, "erreur": None,
                     "etape": "Démarrage de la recherche", "etapes": []})
        etat["etapes"].append({"heure": maintenant(), "texte": "Démarrage de la recherche"})
        ecrire(etat, "recherche démarrée", pousser)
    elif commande == "etape" and len(args) > 1:
        texte = args[1]
        etat.setdefault("etapes", []).append({"heure": maintenant(), "texte": texte, "detail": detail})
        etat["etapes"] = etat["etapes"][-MAX_ETAPES:]
        etat["etape"] = texte
        etat["en_cours"] = True
        ecrire(etat, texte, pousser)
    elif commande == "fin":
        etat["en_cours"] = False
        etat["fin"] = maintenant()
        etat["resume"] = resume
        etat["etape"] = "Recherche terminée"
        etat.setdefault("etapes", []).append({"heure": maintenant(), "texte": "Recherche terminée", "detail": resume})
        ecrire(etat, "recherche terminée", pousser)
    elif commande == "erreur" and len(args) > 1:
        etat["en_cours"] = False
        etat["fin"] = maintenant()
        etat["erreur"] = args[1]
        etat.setdefault("etapes", []).append({"heure": maintenant(), "texte": "Erreur : " + args[1]})
        ecrire(etat, "erreur", pousser)
    else:
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main(sys.argv[1:])
