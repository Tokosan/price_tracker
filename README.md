# price_tracker

Tracker de precios multiusuario y self-hosted. Pegas el link de un producto y te
avisa por Telegram o Discord cuando baja de precio, llega a tu precio objetivo, se
agota o vuelve a haber stock.

Pensado para un grupo chico de personas: sin registro abierto. El admin crea
usuarios con links de invitación y cada uno ve solo lo que sigue.

## Tiendas soportadas

| Tienda | Cómo se lee |
|---|---|
| Steam (tienda de Chile) | API pública de la tienda |
| IKEA Chile | JSON-LD de la página, con selector de variantes (colores) |
| MercadoLibre Chile | API oficial (OAuth; el admin conecta una cuenta desde el panel) |
| Entrejuegos | PrestaShop, detrás de Cloudflare → [FlareSolverr](https://github.com/FlareSolverr/FlareSolverr) |
| DementeGames | PrestaShop |
| La Fortaleza | Jumpseller |
| Lider (supermercado y mercadería general) | Datos de Next.js de la ficha (plataforma de Walmart) |
| Jumbo | API pública del catálogo de VTEX |
| Santa Isabel | API pública del catálogo de VTEX |
| Easy | API pública del catálogo de VTEX, con selector de colores |
| PC Factory | API del catálogo que usa la página (precio por transferencia) |
| Falabella | API de la plataforma Falabella, con selector de variantes (tallas, colores, medidas) |
| Hites | JSON del controlador `Product-Variation` (Salesforce Commerce Cloud), con selector de color y talla |
| Solotodo (comparador) | API pública: el precio más bajo entre tiendas, con o sin reacondicionados |
| Sodimac | API de la plataforma Falabella, con selector de variantes (medidas con precio propio) |
| Tottus | API de la plataforma Falabella (con las zonas de despacho de la página) |
| abc (ex La Polar y AbcDin) | HTML de la ficha (Salesforce Commerce Cloud) |
| Paris | API de commercetools que usa la página, con selector de talla y color |
| Ripley | Datos de Next.js de la ficha, pedida con [curl_cffi](https://github.com/lexiforest/curl_cffi) (Cloudflare bloquea httpx), con selector de tallas |
| Unimarc | BFF del sitio (HTTP/2, detrás de Akamai), con la API de VTEX de respaldo |
| SP Digital | GraphQL de Saleor que usa la página, con curl_cffi (precio por transferencia) |
| Ecofarmacias | Store API de WooCommerce, con selector de variantes (colores, tallas) |
| Salcobrand | JSON-LD de la ficha (Spree), precio Internet, con selector de variantes |

Hay clases base para **PrestaShop**, **Jumpseller**, **VTEX**, **WooCommerce** y la **plataforma Falabella**, así que una tienda nueva con
esas plataformas se agrega en pocas líneas. La app tiene una página `/tiendas` con lo
que soporta cada tienda.

## Funcionalidades

- **Reglas de alerta combinables** por producto:
  - precio objetivo;
  - descuento de al menos X %, contra el precio al empezar a seguirlo, el precio "antes" de la tienda o un precio base que escribes tú;
  - baja o subida desde el último aviso;
  - cada cambio de precio;
  - se agotó;
  - volvió a haber stock.
- **Anti-spam**: histéresis en los umbrales y un solo mensaje por lectura. Las lecturas absurdas (errores de scraping) nunca generan alertas: quedan como anomalías en el panel admin.
- **Un producto, varios links**: la misma cosa en varias tiendas o publicaciones se sigue como un solo producto (hasta 8 links, con nombre propio). Los avisos son por el más barato con stock y dicen en qué tienda está; el gráfico muestra una línea por link. Se puede agregar links al crear el seguimiento, juntar productos que ya sigues o mover un link a otro.
- **Productos compartidos**: si dos usuarios siguen lo mismo, se lee una sola vez y ambos ven el historial completo.
- **Historial de precios** con gráfico, historial de avisos y botón "Revisar ahora" (con cooldown).
- **Panel admin** (dashboard con sidebar): resumen, usuarios e invitaciones, productos (todos, con quién los sigue, y el detalle por usuario) y salud de cada tienda (productos rotos, anomalías). El admin ve qué productos sigue cada usuario; los usuarios entre sí no se ven.
- **Temas** claro/oscuro y paletas verde/azul, guardados por usuario.
- **Scheduler** con intervalo por tienda, jitter, límite de peticiones por dominio y backoff. Tras varios fallos seguidos el producto queda como `broken` y se avisa al admin.

## Stack

- **Backend**: Python 3.13, FastAPI, SQLAlchemy + Alembic, SQLite (WAL), APScheduler en el mismo proceso.
- **Frontend**: React + Vite.
- **Deploy**: Docker Compose detrás de un reverse proxy (hay un ejemplo para Caddy en `deploy/`).

## Desarrollo

Requisitos: [uv](https://docs.astral.sh/uv/) y Node 20+.

```bash
# Backend (desde backend/)
uv sync
uv run pytest -q                      # tests sin red: fixtures reales en tests/fixtures/
uv run ruff check . && uv run ruff format --check .
DATABASE_URL=sqlite:///./data/dev.db uv run alembic upgrade head
DATABASE_URL=sqlite:///./data/dev.db uv run python -m tracker.cli create-admin admin
DATABASE_URL=sqlite:///./data/dev.db uv run python -m tracker.cli invite admin   # link para definir la contraseña
DATABASE_URL=sqlite:///./data/dev.db COOKIE_SECURE=false uv run uvicorn tracker.main:app --reload

# Frontend (desde frontend/): proxy de /api a :8000
npm ci && npm run dev
```

Probar un procesador contra la tienda real:

```bash
uv run python -m tracker.check steam https://store.steampowered.com/app/413150/
uv run python -m tracker.check ikea <url> --save-fixture nombre   # guarda la respuesta como fixture
```

## Deploy

Instrucciones para un servidor Linux nuevo. El backend corre en Docker; el frontend
es estático y lo sirve tu reverse proxy, que también hace de proxy de `/api` al backend.

### Requisitos del servidor

- **Docker Engine** con el plugin **Compose v2** (`docker compose version`).
- **git**, **Node 22** con npm (para construir el frontend), **curl** y **sqlite3**
  (los usan el deploy, los backups y el aviso del auto-deploy).
- Un **reverse proxy con HTTPS**. El ejemplo es para [Caddy](https://caddyserver.com/),
  que saca el certificado solo. Las cookies de sesión son `Secure`: sin HTTPS no se
  puede iniciar sesión (salvo con `COOKIE_SECURE=false`, que es solo para desarrollo).
- Un dominio que apunte al servidor (o a su IP en la VPN, ver [Seguridad](#seguridad)).

### 1. Clonar y configurar

```bash
git clone https://github.com/Tokosan/price_tracker.git ~/price_tracker   # o tu fork
cd ~/price_tracker

cp backend/.env.example backend/.env
chmod 600 backend/.env
python3 -c 'import secrets; print(secrets.token_urlsafe(48))'   # pégalo en SECRET_KEY
```

En `backend/.env`, como mínimo:

| Variable | Valor |
|---|---|
| `SECRET_KEY` | La clave generada arriba (32+ caracteres). **Con una vacía el backend no arranca.** No la cambies después: invalida las sesiones e invitaciones vigentes. |
| `PUBLIC_URL` | La URL con que se entra a la app, sin `/` final (p. ej. `https://tracker.example.com`). Se usa en los links de invitación. |

El resto es opcional (ver [Integraciones](#integraciones)).

Crea la carpeta de datos y un `.env` en la **raíz** del repo (lo lee Docker Compose,
no se versiona) para que el contenedor corra con tu usuario y pueda escribir en `data/`:

```bash
mkdir -p data && chmod 700 data
printf 'TRACKER_UID=%s\nTRACKER_GID=%s\n' "$(id -u)" "$(id -g)" > .env
```

### 2. Levantar el backend

```bash
docker compose -p price_tracker up -d --build
curl -s http://127.0.0.1:8910/api/health        # {"ok": true, ...}
```

Escucha solo en `127.0.0.1:8910`. Las migraciones de la base de datos (SQLite en
`data/tracker.db`) corren solas al arrancar. Si no responde:
`docker compose -p price_tracker logs backend`.

### 3. Construir y publicar el frontend

```bash
cd frontend && npm ci && npm run build && cd ..
sudo mkdir -p /var/www/tracker
sudo cp -a frontend/dist/. /var/www/tracker/
```

### 4. Reverse proxy

Copia el bloque de `deploy/Caddyfile.example` a `/etc/caddy/Caddyfile`, cambia el
dominio y recarga (`sudo systemctl reload caddy`). Con otro proxy la idea es la misma:
`/api/*` va a `http://127.0.0.1:8910` y todo lo demás sale de `/var/www/tracker`, con
`index.html` como respaldo para las rutas del frontend.

### 5. Crear el admin

```bash
docker compose -p price_tracker exec backend python -m tracker.cli create-admin <usuario>
docker compose -p price_tracker exec backend python -m tracker.cli invite <usuario>
```

`invite` imprime un link de un solo uso (dura 48 h) para definir la contraseña.
Ábrelo, elige la contraseña y ya estás dentro. Desde el panel admin se invita al resto
(o con `create-user` + `invite`). `invite` también sirve para resetear una contraseña.

### 6. Comprobar que funciona

Agrega un producto de Steam (no necesita nada extra), p. ej.
`https://store.steampowered.com/app/413150/`, y usa "Revisar ahora". Para probar un
procesador sin la UI:

```bash
docker compose -p price_tracker exec backend python -m tracker.check steam https://store.steampowered.com/app/413150/
```

### Actualizar

`scripts/deploy.sh` hace todo lo anterior de una vez (pull, build del frontend,
publicación atómica, rebuild del backend y espera a `/api/health`):

```bash
# En el servidor:
TRACKER_SSH_HOST=local ./scripts/deploy.sh
# Desde tu máquina, por SSH: copia deploy/deploy.env.example a deploy/deploy.env y
./scripts/deploy.sh [--ref <rama|tag|commit>] [--frontend|--backend]
```

Usa `sudo` para publicar en `TRACKER_WEB_ROOT`: por SSH no hay terminal para pedir la
contraseña, así que tu usuario necesita `sudo` sin contraseña (o corre el script en el
servidor). Los archivos quedan con dueño `TRACKER_WEB_OWNER` (`caddy:caddy` por
defecto; `www-data:www-data` con nginx).

**Un deploy reinicia el contenedor**: se cortan las peticiones en curso.

### Tareas programadas (opcional)

En `deploy/systemd/` hay units con `__USER__` y `__APP_DIR__` como marcadores; el
comentario de cada `.service` tiene el comando para instalarla.

- **Backups** (`tracker-backup.timer`): todos los días a las 04:15 copia la DB con
  `sqlite3 .backup` a `backups/` (7 diarios y 4 semanales). Para restaurar:
  `docker compose -p price_tracker stop backend`, descomprime el backup sobre
  `data/tracker.db` (borra `tracker.db-wal` y `tracker.db-shm` si existen) y vuelve a
  levantarlo. Guarda una copia fuera del servidor.
- **Auto-deploy** (`tracker-autodeploy.timer`): cada minuto, si `origin/main` avanzó,
  lo despliega y avisa por Telegram al admin. **Despliega lo que llegue a `origin`**: si
  clonaste este repo directamente, cualquier commit de upstream llegaría a tu servidor
  sin revisión. Úsalo solo con un `origin` que controles (tu fork).

### Integraciones

- **Telegram**: crea un bot con [@BotFather](https://t.me/BotFather) y pon el token en
  `TELEGRAM_BOT_TOKEN`. Cada usuario lo vincula desde Ajustes con un deep link. Usa long
  polling, así que no hace falta exponer un webhook. Verifica el token con
  `docker compose -p price_tracker exec backend python -m tracker.cli telegram-check`.
- **Discord**: cada usuario pega la URL de un webhook de su servidor.
- **MercadoLibre**: crea una app en el [DevCenter](https://developers.mercadolibre.cl/devcenter)
  con la redirect URI `$PUBLIC_URL/api/admin/meli/callback` (o la que pongas en
  `MELI_REDIRECT_URI`; debe coincidir exacto) y PKCE. Pon `MELI_CLIENT_ID` y
  `MELI_CLIENT_SECRET`, y conecta la cuenta desde el panel admin. Sin esto, la tienda
  queda deshabilitada.
- **FlareSolverr** (solo Entrejuegos, que está detrás de Cloudflare): viene como servicio
  opcional en `docker-compose.yml`. Agrega `COMPOSE_PROFILES=flaresolverr` al `.env` de
  la raíz, pon `FLARESOLVERR_URL=http://flaresolverr:8191/v1` en `backend/.env` y vuelve
  a hacer `docker compose -p price_tracker up -d`. Si ya tienes uno en el host, deja
  `http://host.docker.internal:8191/v1`; no lo publiques en `0.0.0.0` sin firewall: es un
  navegador que pide cualquier URL.

Después de cambiar `backend/.env`: `docker compose -p price_tracker up -d` (recrea el contenedor).

### Seguridad

- **Corre un solo worker** de uvicorn (ya viene así en el `Dockerfile`). El scheduler vive
  en el proceso, y con varios workers se duplicarían las lecturas y las alertas.
- **Pensado para una red privada.** El login no tiene límite de intentos (las contraseñas
  usan argon2 y piden 10+ caracteres, pero eso no frena un ataque sostenido). Lo
  recomendable es publicarlo solo por una VPN (Tailscale, Headscale, WireGuard): pon el
  `bind` a la IP de la VPN en el bloque de Caddy y limita el acceso con sus ACLs. Si lo
  expones a internet, agrega un límite de intentos en el proxy (p. ej. fail2ban sobre
  los 401 de `/api/auth/login`).
- `backend/.env` (`chmod 600`) tiene todos los secretos y `data/` (`chmod 700`) los
  hashes de contraseñas y los tokens de MercadoLibre. Ninguno se versiona.
- El admin ve qué productos sigue cada usuario; los usuarios entre sí no se ven.
