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
| PC Factory | API del catálogo que usa la página (precio por transferencia) |
| Falabella | API de la plataforma Falabella, con selector de variantes (tallas, colores, medidas) |
| Hites | JSON del controlador `Product-Variation` (Salesforce Commerce Cloud), con selector de color y talla |
| Solotodo (comparador) | API pública: el precio más bajo entre tiendas, con o sin reacondicionados |
| Sodimac | API de la plataforma Falabella, con selector de variantes (medidas con precio propio) |
| Tottus | API de la plataforma Falabella (con las zonas de despacho de la página) |

Hay clases base para **PrestaShop**, **Jumpseller**, **VTEX** y la **plataforma Falabella**, así que una tienda nueva con
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

1. Clona el repo en el servidor y crea `backend/.env` a partir de `backend/.env.example` (`chmod 600`).
2. `docker compose up -d --build` levanta el backend en `127.0.0.1:8910`. Las migraciones corren solas.
3. Construye el frontend (`npm ci && npm run build` en `frontend/`) y publica `frontend/dist` en la carpeta que sirve tu reverse proxy. Ver `deploy/Caddyfile.example`.
4. Crea el admin: `docker compose exec backend python -m tracker.cli create-admin <usuario>` y después `… invite <usuario>`.
5. Opcional:
   - `scripts/deploy.sh` para desplegar por SSH (configúralo con `deploy/deploy.env.example`).
   - `deploy/systemd/` para auto-deploy al avanzar `main` y backups diarios de SQLite.

Importante: corre **un solo worker** de uvicorn. El scheduler vive en el proceso, y con varios workers se duplicarían las lecturas y las alertas.

### Integraciones

- **Telegram**: crea un bot con @BotFather y pon el token en `TELEGRAM_BOT_TOKEN`. Cada usuario lo vincula desde Ajustes con un deep link. Usa long polling, así que no hace falta exponer un webhook.
- **Discord**: cada usuario pega la URL de un webhook de su servidor.
- **FlareSolverr**: necesario para Entrejuegos (`FLARESOLVERR_URL`).
- **MercadoLibre**: crea una app en el DevCenter de MercadoLibre con la redirect URI `$PUBLIC_URL/api/admin/meli/callback` y PKCE. Pon `MELI_CLIENT_ID` y `MELI_CLIENT_SECRET`, y conecta la cuenta desde el panel admin.
