#!/usr/bin/env python3
"""Genera data.js (partidos y probabilidades) a partir de The Odds API.

Usa solo la libreria estandar de Python. Necesita la variable de entorno
ODDS_API_KEY. Cada liga activa cuesta 1 credito del plan gratis (500 al mes).
"""
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

API = "https://api.the-odds-api.com/v4"
KEY = os.environ.get("ODDS_API_KEY", "").strip()
DIAS = 8  # cuantos dias hacia adelante mostrar

# (deporte de la pagina, clave de la API, codigo de liga en la pagina)
LIGAS = [
    ("f", "soccer_epl", "PL"),
    ("f", "soccer_spain_la_liga", "LL"),
    ("f", "soccer_italy_serie_a", "SA"),
    ("f", "soccer_germany_bundesliga", "BL"),
    ("f", "soccer_france_ligue_one", "L1"),
    ("f", "soccer_uefa_champs_league", "UCL"),
    ("f", "soccer_usa_mls", "MLS"),
    ("f", "soccer_brazil_campeonato", "BRA"),
    ("b", "baseball_mlb", "MLB"),
    ("k", "basketball_nba", "NBA"),
]

DEPORTES = {
    "f": {
        "n": "Fútbol", "e": "⚽",
        "d": "Top 5 de Europa, Champions League, MLS y Brasileirão",
        "u": 1.08e7,
        "L": {"PL": "Premier League", "LL": "La Liga", "SA": "Serie A",
              "BL": "Bundesliga", "L1": "Ligue 1", "UCL": "Champions League",
              "MLS": "MLS", "BRA": "Brasileirão", "MI": "Mis partidos"},
        "sg": ["Liga Profesional Argentina", "Liga MX", "Liga Nacional de Honduras",
               "Eredivisie", "Primeira Liga", "Premiership de Escocia",
               "Pro League de Bélgica", "Süper Lig", "Championship", "Serie B",
               "Bundesliga 2", "La Liga 2", "J1 League", "K League 1",
               "Saudi Pro League", "A-League", "Copa Libertadores",
               "Copa Sudamericana"],
    },
    "b": {
        "n": "Béisbol", "e": "⚾", "d": "MLB", "u": 1.44e7,
        "L": {"MLB": "MLB", "MI": "Mis partidos"},
        "sg": ["MLB", "LMB de México", "KBO", "NPB", "Liga Dominicana"],
    },
    "k": {
        "n": "Baloncesto", "e": "🏀", "d": "NBA", "u": 1.44e7,
        "L": {"NBA": "NBA", "MI": "Mis partidos"},
        "sg": ["NBA", "EuroLeague", "NBA G League", "NCAA", "Liga ACB"],
    },
}

NOMBRES = {
    "Manchester United": "Man. United", "Manchester City": "Man. City",
    "Brighton and Hove Albion": "Brighton", "Wolverhampton Wanderers": "Wolves",
    "Tottenham Hotspur": "Tottenham", "Nottingham Forest": "Nottingham F.",
    "Newcastle United": "Newcastle", "West Ham United": "West Ham",
    "Leeds United": "Leeds", "Paris Saint Germain": "PSG",
    "Paris Saint-Germain": "PSG", "Atlético Madrid": "Atlético Madrid",
}
APODOS_2 = ("Trail Blazers", "Red Sox", "White Sox", "Blue Jays")


def corto(nombre, dep):
    if dep == "f":
        if nombre in NOMBRES:
            return NOMBRES[nombre]
        return re.sub(r"^(FC|AFC) | (FC|AFC)$", "", nombre).strip()
    for apodo in APODOS_2:  # NBA y MLB: solo el apodo del equipo
        if nombre.endswith(apodo):
            return apodo
    return nombre.split()[-1]


def pedir(ruta, **params):
    params["apiKey"] = KEY
    url = f"{API}{ruta}?{urllib.parse.urlencode(params)}"
    with urllib.request.urlopen(url, timeout=30) as r:
        quedan = r.headers.get("x-requests-remaining")
        return json.loads(r.read().decode("utf-8")), quedan


def probabilidades(ev, tres_vias):
    """Promedia las probabilidades de todas las casas, sin el margen."""
    local, visita = ev["home_team"], ev["away_team"]
    todas = []
    for casa in ev.get("bookmakers", []):
        for mercado in casa.get("markets", []):
            if mercado.get("key") != "h2h":
                continue
            cuota = {o["name"]: o["price"] for o in mercado.get("outcomes", [])}
            try:
                inv = ([1 / cuota[local], 1 / cuota["Draw"], 1 / cuota[visita]]
                       if tres_vias else [1 / cuota[local], 1 / cuota[visita]])
            except (KeyError, ZeroDivisionError, TypeError):
                continue
            total = sum(inv)
            todas.append([x / total for x in inv])
    if not todas:
        return None
    p = [round(sum(t[i] for t in todas) / len(todas) * 100, 1)
         for i in range(len(todas[0]))]
    p[-1] = round(100 - sum(p[:-1]), 1)  # que sumen exactamente 100
    return p


def filas_de(dep, liga, eventos, ahora):
    desde, hasta = ahora - timedelta(hours=4), ahora + timedelta(days=DIAS)
    filas = []
    for ev in eventos:
        try:
            t = datetime.strptime(ev["commence_time"], "%Y-%m-%dT%H:%M:%SZ")
            t = t.replace(tzinfo=timezone.utc)
        except (KeyError, ValueError):
            continue
        if not (desde <= t <= hasta):
            continue
        p = probabilidades(ev, tres_vias=(dep == "f"))
        if not p:
            continue
        fila = [liga, t.strftime("%m-%dT%H:%M"),
                corto(ev["home_team"], dep), corto(ev["away_team"], dep)] + p
        filas.append((t, fila))
    return filas


def main():
    if not KEY:
        sys.exit("Falta ODDS_API_KEY (el secreto del repositorio).")
    ahora = datetime.now(timezone.utc)

    activas, _ = pedir("/sports")  # esta consulta no gasta creditos
    activas = {s["key"] for s in activas if s.get("active")}

    filas = {"f": [], "b": [], "k": []}
    ok = 0
    for dep, clave, liga in LIGAS:
        if clave not in activas:
            print(f"- {liga}: fuera de temporada, la salto")
            continue
        try:
            eventos, quedan = pedir(f"/sports/{clave}/odds", regions="eu",
                                    markets="h2h", oddsFormat="decimal",
                                    dateFormat="iso")
        except (urllib.error.URLError, TimeoutError, ValueError) as e:
            print(f"- {liga}: ERROR {e}")
            continue
        nuevas = filas_de(dep, liga, eventos, ahora)
        filas[dep] += nuevas
        ok += 1
        print(f"- {liga}: {len(nuevas)} partidos (creditos restantes: {quedan})")

    if ok == 0:
        sys.exit("Ninguna liga respondio; no toco data.js.")

    S = {}
    for dep, info in DEPORTES.items():
        info = dict(info)
        info["note"] = "" if filas[dep] else "Sin partidos con cuotas publicadas por ahora."
        info["D"] = [f for _, f in sorted(filas[dep], key=lambda x: x[0])]
        info["V"] = []
        S[dep] = info

    js = ("const S=" + json.dumps(S, ensure_ascii=False, separators=(",", ":"))
          + ";\nconst SNAP=new Date(\""
          + ahora.strftime("%Y-%m-%dT%H:%M:%SZ") + "\");\n")
    with open("data.js", "w", encoding="utf-8") as f:
        f.write(js)
    total = sum(len(v) for v in filas.values())
    print(f"Listo: {total} partidos guardados en data.js")


if __name__ == "__main__":
    main()
