# Mis Pollas Mundial 2026 ⚽

App única para seguir mis **5 pollas** del Mundial 2026 (en 4 sites con reglas distintas)
desde un icono en el celular: marcadores que puse en cada juego de hoy/mañana,
mi puntaje, el del líder y mi posición en cada polla. Los standings se refrescan solos.

## Qué hay aquí
```
index.html              La app (PWA) — se ve en el cel
manifest.webmanifest    Para instalar el icono en Android
sw.js                   Funciona offline / abre rápido
icons/                  Iconos del icono de la app
data/
  matches.json          Los 72 partidos + mis 5 pronósticos (sale del Excel)
  config.json           Las 5 pollas (site, cuenta, reglas, color)
  standings.json        Mi puntaje / líder / posición — lo actualiza el robot
scraper/scrape.py       El robot que lee los 4 sites
.github/workflows/refresh.yml   Corre el robot cada 3h en la nube (GitHub Actions)
```

## Las 5 pollas
| Columna Excel | Site | Cuenta | Reglas |
|---|---|---|---|
| Colombia | PollaPato | ElGanado | exacto 1pt + 1º/2º grupo + podio |
| Panamá | Polla26 | Belfort | exacto 3 / ganador 1 |
| AAA1 | PollaTripleA | dzebede | exacto 3 / ganador 1 |
| AAA2 | PollaTripleA | dzebede (2) | exacto 3 / ganador 1 |
| Claude | Kicktipp | Belfort | tendencia 2 / dif 3 / exacto 4 |

## Puesta en marcha (GitHub) — pasos
1. **Crear cuenta** en https://github.com (gratis).
2. **Crear un repositorio** nuevo, ej. `mis-pollas-2026` (público o privado; para GitHub
   Pages gratis en repo privado también sirve).
3. **Subir estos archivos** al repo (te guío: o por la web "Add file → Upload files",
   o con `git push`).
4. **Settings → Secrets and variables → Actions → New repository secret**, y crear:
   - `P26_EMAIL`, `P26_PASS`
   - `TRIPLEA_EMAIL`, `TRIPLEA_PASS`
   - `POLLAPATO_EMAIL`, `POLLAPATO_PASS`
   (Kicktipp es público, no necesita secret.)
5. **Settings → Pages → Source: Deploy from a branch → `main` / root.** Eso te da la URL
   pública (ej. `https://TUUSUARIO.github.io/mis-pollas-2026/`).
6. **Actions → "Refrescar standings" → Run workflow** para la primera corrida (luego
   corre solo cada 3 horas).

## Icono en Android
1. Abre la URL de Pages en **Chrome** del celular.
2. Menú **⋮ → "Agregar a pantalla de inicio"** (o "Instalar app").
3. Listo: queda el icono del balón en tu homepage; abre en pantalla completa.

## Refrescar a mano (opcional)
En **Actions → Refrescar standings → Run workflow**. O localmente:
```
pip install playwright && python -m playwright install chromium
export P26_EMAIL=... P26_PASS=... TRIPLEA_EMAIL=... TRIPLEA_PASS=... POLLAPATO_EMAIL=... POLLAPATO_PASS=...
python scraper/scrape.py
```

## Regenerar pronósticos desde el Excel
Si cambias el Excel: `python scraper/build_matches.py` (regenera `data/matches.json`).

## Nota de seguridad
Las contraseñas de los sites viven sólo como **GitHub Secrets** (cifrados, no visibles en
el repo ni en logs). El robot las usa para entrar y leer tus standings; no hace nada más.
