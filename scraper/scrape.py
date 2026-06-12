#!/usr/bin/env python3
"""
Scraper de las 5 pollas -> data/standings.json
Fuentes:
  - Kicktipp  : ranking público (requests)
  - Polla26   : login Laravel (requests + cookies)
  - PollaTripleA (AAA1 y AAA2): login + API Supabase v_leaderboard (Playwright)
  - PollaPato : login Firebase + dashboard (Playwright)

Credenciales por variables de entorno (GitHub Secrets):
  P26_EMAIL, P26_PASS
  TRIPLEA_EMAIL, TRIPLEA_PASS
  POLLAPATO_EMAIL, POLLAPATO_PASS
Kicktipp es público (no necesita credenciales).

Filosofía: si un site falla, se conserva el último valor bueno de standings.json
y se marca su 'ok': false. Nunca se borra data por un fallo puntual.
"""
import os, re, json, sys, time, html as ihtml
import urllib.request, urllib.parse, http.cookiejar
from datetime import datetime, timezone, timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "data", "standings.json")
MATCHES_JSON = os.path.join(ROOT, "data", "matches.json")
PANAMA = timezone(timedelta(hours=-5))

# nombres que difieren entre Kicktipp y el Excel
KICK_ALIAS = {"EE.UU.": "Estados Unidos", "Curaçao": "Curazao", "DR Congo": "RD del Congo"}
def _norm(name): n = name.strip(); return KICK_ALIAS.get(n, n)

def log(*a): print("[scrape]", *a, file=sys.stderr)

def ua_opener():
    cj = http.cookiejar.CookieJar()
    op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
    op.addheaders = [('User-Agent', 'Mozilla/5.0 (compatible; PollasBot/1.0)')]
    return op, cj

def strip_html(h):
    return ihtml.unescape(re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', h)))

# ----------------------------------------------------------------------------
# 1) KICKTIPP (público)
# ----------------------------------------------------------------------------
def scrape_kicktipp():
    url = "https://www.kicktipp.es/mundial-masters-birriosos-2026/ranking"
    op, _ = ua_opener()
    html = op.open(url, timeout=30).read().decode('utf-8', 'ignore')
    rows = re.findall(r'<tr class="clickable kicktipp-pos\d+ teilnehmer.*?</tr>', html, re.S)
    parsed = []
    for r in rows:
        n = re.search(r'mg_name">([^<]+)', r)
        p = re.search(r'class="position[^"]*"><div>(\d+)', r)
        g = re.findall(r'gesamtpunkte[^>]*">(\d+)', r)
        if n and g:
            parsed.append({"pos": int(p.group(1)) if p else None,
                           "name": n.group(1).strip(), "pts": int(g[-1])})
    if not parsed:
        raise RuntimeError("kicktipp: no se parsearon filas")
    leader = parsed[0]
    me = next((x for x in parsed if x["name"].strip().lower() == "belfort"), None)
    if not me:
        raise RuntimeError("kicktipp: no se encontró Belfort en el top mostrado")
    return {"kicktipp": {"myPoints": me["pts"], "myRank": me["pos"],
                          "leaderPoints": leader["pts"], "leaderName": leader["name"],
                          "participants": None, "ok": True}}

# ----------------------------------------------------------------------------
# 1b) RESULTADOS REALES (Kicktipp tippuebersicht, público) -> data/matches.json
# ----------------------------------------------------------------------------
def scrape_results():
    base = "https://www.kicktipp.es/mundial-masters-birriosos-2026/tippuebersicht"
    op, _ = ua_opener()
    results, seen = {}, set()
    for idx in range(1, 19):
        h = op.open(base + f"?spieltagIndex={idx}", timeout=30).read().decode("utf-8", "ignore")
        rows = re.findall(r'<tr class="clickable"[^>]*>(.*?)</tr>', h, re.S)
        if not rows: break
        for r in rows:
            tds = re.findall(r'<td[^>]*>(.*?)</td>', r, re.S)
            if len(tds) < 5: continue
            local = _norm(strip_html(tds[1])); visit = _norm(strip_html(tds[2]))
            if (local, visit) in seen: continue
            seen.add((local, visit))
            m = re.search(r'(\d+)\s*:\s*(\d+)', strip_html(tds[4]))
            if m: results[(local.lower(), visit.lower())] = [int(m.group(1)), int(m.group(2))]
    if not results:
        raise RuntimeError("resultados: Kicktipp no devolvió ninguno")
    data = json.load(open(MATCHES_JSON, encoding="utf-8"))
    applied = 0
    for mt in data["matches"]:
        res = results.get((mt["home"].lower(), mt["away"].lower()))
        if res is not None and mt.get("result") != res:
            mt["result"] = res; applied += 1
    json.dump(data, open(MATCHES_JSON, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    return applied

# ----------------------------------------------------------------------------
# 2) POLLA26 (Laravel, login por cookies)
# ----------------------------------------------------------------------------
def scrape_polla26():
    email = os.environ["P26_EMAIL"]; pw = os.environ["P26_PASS"]
    op, _ = ua_opener()
    page = op.open("https://polla26.com/login", timeout=30).read().decode('utf-8', 'ignore')
    m = re.search(r'name="_token"[^>]*value="([^"]+)"', page) or \
        re.search(r'value="([^"]+)"[^>]*name="_token"', page)
    if not m: raise RuntimeError("polla26: no CSRF token")
    data = urllib.parse.urlencode({"_token": m.group(1), "email": email,
                                   "password": pw, "remember": "on"}).encode()
    req = urllib.request.Request("https://polla26.com/login", data=data,
        headers={'User-Agent': 'Mozilla/5.0', 'Referer': 'https://polla26.com/login',
                 'Content-Type': 'application/x-www-form-urlencoded'})
    op.open(req, timeout=30)
    dash = op.open("https://polla26.com/dashboard", timeout=30).read().decode('utf-8', 'ignore')
    txt = strip_html(dash)
    # líder: primer nombre tras la medalla 🥇 con su puntaje
    lead = re.search(r'Top 10 Pollas.*?🥇\s*(.+?)\s+(\d+)\s+Ver', txt)
    leaderName = lead.group(1).strip() if lead else None
    leaderPts = int(lead.group(2)) if lead else None
    # mi polla "Belfort": número antes de "Ver" en la fila de Mis Pollas
    reg = txt[txt.find("Mis Pollas"): txt.find("Top 10")] or txt
    mine = re.search(r'Belfort\s+\S+\s+(\d+)\s+Ver', reg) or re.search(r'Belfort[^\d]{0,20}(\d+)', reg)
    myPts = int(mine.group(1)) if mine else None
    parts = re.search(r'PARTICIPANTES\s*(\d+)', txt)
    if myPts is None: raise RuntimeError("polla26: no se halló puntaje de Belfort")
    return {"polla26": {"myPoints": myPts, "myRank": None, "leaderPoints": leaderPts,
                         "leaderName": leaderName,
                         "participants": int(parts.group(1)) if parts else None, "ok": True}}

# ----------------------------------------------------------------------------
# Playwright helpers (PollaTripleA y PollaPato)
# ----------------------------------------------------------------------------
def _pw():
    from playwright.sync_api import sync_playwright
    return sync_playwright()

def _fill_login(page, email, pw):
    """Rellena email/password de forma resiliente y envía."""
    page.wait_for_timeout(1500)
    # email
    for sel in ['input[type=email]', 'input[name=email]', 'input[name=correo]',
                'input[autocomplete=username]', 'input[type=text]']:
        if page.locator(sel).count():
            page.locator(sel).first.fill(email); break
    # password
    for sel in ['input[type=password]', 'input[name=password]', 'input[name=clave]']:
        if page.locator(sel).count():
            page.locator(sel).first.fill(pw); break
    # submit
    for sel in ['button[type=submit]', 'button:has-text("Iniciar")', 'button:has-text("Entrar")',
                'button:has-text("Ingresar")', 'button:has-text("Login")', 'input[type=submit]']:
        if page.locator(sel).count():
            page.locator(sel).first.click(); return
    page.keyboard.press("Enter")

# ----------------------------------------------------------------------------
# 3) POLLATRIPLEA (Next.js + Supabase) -> AAA1 (dzebede) y AAA2 (dzebede (2))
# ----------------------------------------------------------------------------
SUPA_LB = ("https://knvsrupdwokzgceacpro.supabase.co/rest/v1/v_leaderboard"
           "?select=sub_username,total_points,rank,exact_count,predictions_count"
           "&predictions_count=eq.72&order=total_points.desc,exact_count.desc")

def scrape_triplea():
    """Login (Playwright) sólo para capturar las cabeceras de sesión de Supabase,
    luego se pagina el leaderboard completo por REST (la tabla puede tener >1000 filas)."""
    email = os.environ["TRIPLEA_EMAIL"]; pw = os.environ["TRIPLEA_PASS"]
    hdrs = {}
    with _pw() as p:
        b = p.chromium.launch(headless=True)
        ctx = b.new_context(user_agent="Mozilla/5.0")
        page = ctx.new_page()
        def on_req(req):
            if "v_leaderboard" in req.url and "apikey" not in hdrs:
                h = req.headers
                for k in ("apikey", "authorization"):
                    if k in h: hdrs[k] = h[k]
        page.on("request", on_req)
        page.goto("https://pollatriplea.com/login", wait_until="domcontentloaded", timeout=45000)
        _fill_login(page, email, pw)
        page.wait_for_timeout(4000)
        page.goto("https://pollatriplea.com/tabla", wait_until="domcontentloaded", timeout=45000)
        page.wait_for_timeout(4000)
        b.close()
    if "apikey" not in hdrs:
        raise RuntimeError("triplea: no se capturaron cabeceras de sesión")
    # paginar leaderboard completo
    rows, off = [], 0
    while True:
        url = SUPA_LB + f"&offset={off}&limit=1000"
        req = urllib.request.Request(url, headers={**hdrs, "User-Agent": "Mozilla/5.0"})
        chunk = json.load(urllib.request.urlopen(req, timeout=30))
        rows += chunk
        if len(chunk) < 1000: break
        off += 1000
    if not rows: raise RuntimeError("triplea: leaderboard vacío")
    leader = rows[0]
    out = {}
    for pid, alias in (("triplea", "dzebede"), ("triplea2", "dzebede (2)")):
        m = next((r for r in rows if (r.get("sub_username") or "").strip().lower() == alias.lower()), None)
        if m:
            out[pid] = {"myPoints": m.get("total_points"), "myRank": m.get("rank"),
                        "leaderPoints": leader.get("total_points"),
                        "leaderName": leader.get("sub_username"),
                        "participants": len(rows), "ok": True}
        else:
            out[pid] = {"ok": False, "error": f"no encontré {alias}"}
    return out

# ----------------------------------------------------------------------------
# 4) POLLAPATO (Firebase) -> Colombia (ElGanado)
# ----------------------------------------------------------------------------
def scrape_pollapato():
    email = os.environ["POLLAPATO_EMAIL"]; pw = os.environ["POLLAPATO_PASS"]
    with _pw() as p:
        b = p.chromium.launch(headless=True)
        ctx = b.new_context(user_agent="Mozilla/5.0")
        page = ctx.new_page()
        page.goto("https://pollapato.com/login", wait_until="domcontentloaded", timeout=45000)
        _fill_login(page, email, pw)
        page.wait_for_timeout(5000)
        page.goto("https://pollapato.com/dashboard", wait_until="domcontentloaded", timeout=45000)
        page.wait_for_timeout(3500)
        dash = page.inner_text("body")
        parts = None
        mp = re.search(r'(\d+)\s*PARTICIPANTES', re.sub(r'\s+', ' ', dash))
        if mp: parts = int(mp.group(1))
        # leaderboard: primera fila -> líder (col 0 = nombre, col 1 = Pts)
        leaderPts = None; leaderName = None
        try:
            page.goto("https://pollapato.com/polla/mundial_2026/leaderboard",
                      wait_until="domcontentloaded", timeout=45000)
            page.wait_for_timeout(4500)
            r0 = page.locator("table tbody tr").first
            leaderName = r0.locator("td").nth(0).inner_text().strip()
            leaderPts = int(re.search(r'\d+', r0.locator("td").nth(1).inner_text()).group())
        except Exception as e:
            log("pollapato leaderboard:", e)
        b.close()
    # parsear dashboard: "ElGanado RANKING #69 PUNTOS 1 PREDICCIONES 88/88"
    t = re.sub(r'\s+', ' ', dash)
    def entry(name):
        m = re.search(re.escape(name) + r'\s*RANKING\s*#?(\d+)\s*PUNTOS\s*(\d+)', t, re.I)
        if m: return int(m.group(1)), int(m.group(2))
        return None, None
    rank, pts = entry("ElGanado")
    if pts is None:
        raise RuntimeError("pollapato: no se parseó ElGanado del dashboard")
    return {"pollapato": {"myPoints": pts, "myRank": rank, "leaderPoints": leaderPts,
                          "leaderName": leaderName, "participants": parts, "ok": True}}

# ----------------------------------------------------------------------------
# MAIN
# ----------------------------------------------------------------------------
def main():
    # cargar último standings (para conservar valores si algo falla)
    try:
        prev = json.load(open(OUT, encoding="utf-8"))
    except Exception:
        prev = {"pollas": {}}
    result = dict(prev.get("pollas", {}))

    jobs = [("kicktipp", scrape_kicktipp), ("polla26", scrape_polla26),
            ("triplea", scrape_triplea), ("pollapato", scrape_pollapato)]
    status = {}
    for label, fn in jobs:
        try:
            upd = fn()
            for pid, val in upd.items():
                # fusionar sobre lo previo (no perder participants/etc.)
                merged = dict(result.get(pid, {}))
                merged.update({k: v for k, v in val.items() if v is not None or k == "ok"})
                if val.get("ok"): merged.pop("error", None)   # limpiar error viejo al tener éxito
                result[pid] = merged
            status[label] = "ok"
            log(label, "OK")
        except Exception as e:
            status[label] = f"FALLO: {e}"
            if label in result: result[label].setdefault("ok", False)
            log(label, "FALLO:", e)

    # resultados reales de los partidos (actualiza data/matches.json)
    try:
        n = scrape_results()
        status["resultados"] = f"ok ({n} aplicados)"
        log("resultados OK:", n, "aplicados")
    except Exception as e:
        status["resultados"] = f"FALLO: {e}"
        log("resultados FALLO:", e)

    out = {"updated": datetime.now(PANAMA).isoformat(timespec="seconds"),
           "source": "scraper", "status": status, "pollas": result}
    json.dump(out, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    log("escrito", OUT)
    log("status:", json.dumps(status, ensure_ascii=False))

if __name__ == "__main__":
    main()
