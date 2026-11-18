# Bloque 1 · Servidor y bot · Plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Recepción de datos de la tablet en lnk-server (FastAPI + SQLite detrás de Tailscale Funnel) y bot de Telegram propio con `/donde`.

**Architecture:** Una imagen Python con dos servicios en un `docker-compose.yml` en la raíz del repo: `api` (FastAPI, `POST /api/v1/ingest`) y `bot` (long polling con httpx). Comparten un SQLite en `./data`. La lógica de `/donde` son funciones puras en `location.py`.

**Tech Stack:** Python 3.12, uv, FastAPI, pydantic v2, uvicorn, httpx, pytest, sqlite3 (biblioteca estándar), Podman.

**Spec:** `docs/superpowers/specs/2026-11-18-cadena-tablet-servidor-design.md`. Las secciones 4 (contrato) y 5 (servidor) son normativas.

**Plan hermano:** `docs/superpowers/plans/2026-11-18-bloque1-app-android.md`. Comparte la tarea 1 (contrato); ningún otro fichero.

## Global Constraints

- Ruta única pública: `POST /api/v1/ingest`. Cuerpo ≤ 256 KB (262144 bytes) y ≤ 500 registros.
- `ts` válido: `1704067200000` (2024-01-01T00:00:00Z) ≤ ts ≤ ahora + 300000 ms.
- `device_id` `^[a-z0-9-]{1,64}$`; `app_version` ≤ 32 caracteres; claves OBD `^[a-z0-9_]{1,32}$`; códigos DTC `^[PCBU][0-9A-F]{4}$`; `detail` ≤ 200 caracteres.
- Eventos: `session_start`, `resumed`, `obd_connected`, `obd_lost`, `obd_error`.
- Variables de entorno: `CAR_TRACE_INGEST_TOKEN` (api), `CAR_TRACE_BOT_TOKEN` y `CHAT_ID` (bot), `CAR_TRACE_DB` (por defecto `/data/car-trace.db`), `CAR_TRACE_TZ` (por defecto `Europe/Madrid`).
- Puerto en el host: 8090 → 8000 del contenedor, solo en `127.0.0.1` y `<TAILSCALE_IP>`.
- Nunca escribir secretos en el repo, en los logs ni en el brain.
- Los commits siguen github-standard: ramas `feat/…` desde `develop`, formato `tipo: emoji descripción` en inglés.
- Los tests se ejecutan con `cd server && uv run pytest -q`.

## Review Focus

1. **Ids repetidos dentro del mismo lote.** El segundo cuenta como `duplicates`, no como error (test en la tarea 3).
2. **Cuerpo sin `Content-Length`** (chunked) de más de 256 KB. Debe responder `413` sin cargarlo entero en memoria (test en la tarea 3).
3. **`/donde` con datos pero sin ningún punto GPS válido** (OBD sin fix, o solo puntos imprecisos). Debe responder con el estado y "Sin posición GPS todavía.", sin ubicación (test en la tarea 5).
4. **Actualizaciones de Telegram que no son mensajes de texto** (fotos, mensajes editados, otros chats, callbacks). Se ignoran sin que el bucle se caiga (test en la tarea 6).
5. **Petición por Funnel a `/api/v1/ingest/` (barra final) o con método distinto de POST.** No debe abrir otras rutas: `404` o `405`, nunca otra respuesta de la API (test en la tarea 4).

---

### Task 1: Contrato v1 y ejemplos compartidos

**Files:**
- Create: `docs/contract/ingest-v1.md`
- Create: `docs/contract/examples/valid-mixed.json`, `partial-reject.json`, `batch-missing-device.json`, `batch-not-json.txt`
- Create: `docs/contract/examples/README.md`

**Interfaces:**
- Produces: el formato de los ficheros de ejemplo, que usan los tests de las tareas 3 (servidor) y B2 (app):
  ```json
  {"description": "…", "request": { /* lote completo */ },
   "expected_status": 200,
   "expected": {"accepted": 4, "duplicates": 0, "rejected_indexes": []}}
  ```
  Para el `400`, `expected` es `null`. `batch-not-json.txt` es un cuerpo crudo que debe dar `400`.

- [ ] **Step 1:** Escribir `ingest-v1.md` copiando literalmente las tablas 4.1–4.3 de la spec. Añadir una sección "Versionado": cualquier cambio incompatible crea `/api/v2/ingest`.
- [ ] **Step 2:** `valid-mixed.json` con 6 registros válidos de una misma sesión: `event session_start`, `dtc` (active `["P0401"]`), 2 `gps` (uno sin campos opcionales), 1 `obd` con todas las claves conocidas y 1 `obd` con una clave desconocida `boost_extra`. Resultado esperado: `accepted 6`.
- [ ] **Step 3:** `partial-reject.json` con 7 registros: 3 válidos, uno con `ts` 946684800000 (año 2000), uno `gps` con `lat` 91, uno `dtc` con código `X1234` y uno con el mismo `id` que el primero. Esperado: `accepted 3`, `duplicates 1`, `rejected_indexes [3,4,5]`.
- [ ] **Step 4:** `batch-missing-device.json`, sin `device_id` (esperado `400`), y `batch-not-json.txt` con `{"device_id": "junsun-307", "records": [`.
- [ ] **Step 5:** Validar que los `.json` se parsean: `for f in docs/contract/examples/*.json; do python3 -m json.tool "$f" >/dev/null || echo BAD $f; done`. Esperado: sin salida.
- [ ] **Step 6:** Commit en `feat/contract-v1`: `docs: 📝 add ingest contract v1 and shared examples`. Integrar en `develop` antes de empezar las tareas 3 y B2.

### Task 2: Esqueleto del servidor, configuración y modelos del contrato

**Files:**
- Create: `server/pyproject.toml`, `server/.python-version` (`3.12`), `server/app/__init__.py`, `server/app/config.py`, `server/app/contract.py`
- Test: `server/tests/test_contract.py`

**Interfaces:**
- Produces:
  - `config.Settings` (dataclass congelada) con `ingest_token: str`, `bot_token: str`, `chat_id: int | None`, `db_path: str`, `tz: str`, y `Settings.from_env() -> Settings`. Una variable vacía queda como `""` o `None`; cada servicio valida solo las suyas al arrancar.
  - `contract.Batch(device_id: str, app_version: str, records: list[dict])`: valida solo la forma del lote (los registros se validan uno a uno, porque el rechazo es parcial). Máximo 500 registros.
  - `contract.parse_record(raw: dict, now_ms: int) -> Record`, que lanza `RecordError(str)`. `Record` es una unión discriminada por `type` de `GpsRecord | ObdRecord | DtcRecord | EventRecord`, con campos comunes `id: UUID`, `session_id: UUID`, `seq: int`, `ts: int` y `type`.
  - `Record.payload() -> dict`: los campos propios del tipo (lo que va a la columna `data`).

- [ ] **Step 1:** `uv init --app --no-workspace server`, ajustar `requires-python = ">=3.12"` y `uv add fastapi pydantic uvicorn httpx` y `uv add --dev pytest`.
- [ ] **Step 2: Tests que fallan** en `test_contract.py`:
  - `test_valid_mixed_example_parses`: carga `../docs/contract/examples/valid-mixed.json` y `parse_record` funciona en los 6 registros; el `obd` con `boost_extra` conserva la clave en `payload()`.
  - `test_rejects_out_of_range` (parametrizado): `ts` 946684800000 → `RecordError`; `ts` = now + 300001 → `RecordError`; `lat` 91; `bearing` 360; `acc_m` -1; DTC `X1234`; `event` `"reboot"`; `detail` de 201 caracteres; `values` `{}`; clave `"RPM"`; valor `"850"` (texto).
  - `test_ts_upper_bound_inclusive`: now + 300000 se acepta.
  - `test_batch_rejects_501_records` y `test_batch_rejects_bad_device_id` (`"Junsun 307"`).
- [ ] **Step 3:** Ejecutar `cd server && uv run pytest -q tests/test_contract.py`. Esperado: FAIL (falta el módulo).
- [ ] **Step 4:** Implementar `config.py` y `contract.py` con pydantic v2 (`Field(ge=…, le=…)`, `pattern=`, `Literal`, `TypeAdapter` para la unión discriminada; `extra="forbid"` en los registros salvo dentro de `values`). Los límites de `ts` se comprueban en `parse_record` con el `now_ms` recibido.
- [ ] **Step 5:** Ejecutar los tests. Esperado: PASS.
- [ ] **Step 6:** Commit en `feat/server-ingest`: `feat: ✨ add server settings and contract v1 models`.

### Task 3: Base de datos y `POST /api/v1/ingest`

**Files:**
- Create: `server/app/db.py`, `server/app/ingest.py`, `server/app/main.py` (versión mínima: crea la app e incluye el router)
- Test: `server/tests/test_db.py`, `server/tests/test_ingest.py`, `server/tests/conftest.py`

**Interfaces:**
- Consumes: `Settings`, `Batch` y `parse_record` de la tarea 2.
- Produces:
  - `db.connect(path: str) -> sqlite3.Connection`, con `journal_mode=WAL`, `busy_timeout=5000` y el esquema 5.2 de la spec más `schema_version(version INTEGER)` con valor 1, todo idempotente.
  - `db.insert_records(conn, device_id: str, records: list[Record], received_at_ms: int) -> tuple[int, int]` (aceptados, duplicados), en una sola transacción con `INSERT OR IGNORE`.
  - `main.create_app(settings: Settings, clock: Callable[[], int] = now_ms) -> FastAPI`, con la conexión en `app.state.db` y el reloj en `app.state.clock`.
  - `conftest.py`: fixture `client(tmp_path)` con el token `"test-token"` y reloj fijo `1763481600000`.

- [ ] **Step 1: Tests que fallan** en `test_db.py`: `test_connect_is_idempotent` (dos `connect` sobre el mismo fichero) y `test_wal_enabled`.
- [ ] **Step 2: Tests que fallan** en `test_ingest.py`:
  - `test_contract_examples` (parametrizado sobre los `.json` de `docs/contract/examples/`): el estado y `accepted`, `duplicates` y los índices rechazados coinciden con `expected`.
  - `test_not_json_body_is_400` con `batch-not-json.txt`.
  - `test_resend_counts_as_duplicates`: enviar `valid-mixed` dos veces → la segunda da `accepted 0` y `duplicates 6`, y la tabla sigue con 6 filas.
  - `test_duplicate_ids_within_batch` (Review Focus 1).
  - `test_missing_or_wrong_token_is_401` (sin cabecera, `Bearer x`, `Basic test-token`).
  - `test_content_length_over_limit_is_413` (262145 bytes) y `test_chunked_body_over_limit_is_413`, que envía un generador sin `Content-Length` (Review Focus 2).
  - `test_rejected_entries_carry_index_id_and_error`.
- [ ] **Step 3:** Ejecutar `uv run pytest -q`. Esperado: FAIL.
- [ ] **Step 4:** Implementar `db.py` e `ingest.py`. El token se comprueba antes de leer el cuerpo, con `hmac.compare_digest`. El cuerpo se lee con `request.stream()` acumulando bytes y se corta con `413` al pasar de 262144. Las respuestas siguen la tabla 4.3; cada rechazo es `{"index": i, "id": raw.get("id"), "error": str}`.
- [ ] **Step 5:** Ejecutar los tests. Esperado: PASS.
- [ ] **Step 6:** Commit: `feat: ✨ add sqlite storage and ingest endpoint`.

### Task 4: `funnel_guard` y la app de producción

**Files:**
- Create: `server/app/funnel_guard.py`
- Modify: `server/app/main.py` (añadir el middleware, `docs_url=None`, `redoc_url=None`, `openapi_url=None` y `GET /healthz` → `{"ok": true}` solo para la red interna)
- Test: `server/tests/test_funnel_guard.py`

**Interfaces:**
- Consumes: `create_app` de la tarea 3.
- Produces: `funnel_guard.FunnelGuardMiddleware`, un middleware ASGI. Si la petición trae `X-Forwarded-Host` y la ruta no es exactamente `/api/v1/ingest`, responde `404` sin llamar a la app.

- [ ] **Step 1: Tests que fallan:**
  - `test_forwarded_request_to_healthz_is_404`;
  - `test_forwarded_request_to_ingest_reaches_app` (sin token → `401`, lo que demuestra que llegó a la app);
  - `test_direct_request_to_healthz_is_200`;
  - `test_forwarded_trailing_slash_is_404` y `test_forwarded_get_ingest_is_405_or_404` (Review Focus 5);
  - `test_docs_and_openapi_are_404`.
- [ ] **Step 2:** Ejecutar. Esperado: FAIL.
- [ ] **Step 3:** Implementar el middleware y los cambios en `main.py`. Añadir `server/app/__main__.py`, que arranca uvicorn en `0.0.0.0:8000` con `create_app(Settings.from_env())` y termina con error si `ingest_token` está vacío.
- [ ] **Step 4:** Ejecutar. Esperado: PASS.
- [ ] **Step 5:** Commit: `feat: ✨ restrict funnel traffic to the ingest route`. Integrar `feat/server-ingest` en `develop`.

### Task 5: Lógica de `/donde`

**Files:**
- Create: `server/app/location.py`
- Test: `server/tests/test_location.py`

**Interfaces:**
- Consumes: `db.connect` y el esquema de la tarea 3 (solo lectura).
- Produces:
  - `GpsPoint(ts: int, lat: float, lon: float, acc_m: float, speed_mps: float | None)`.
  - `last_valid_point(points_newest_first: list[GpsPoint]) -> GpsPoint | None`: acepta `acc_m` ≤ 50, no `abs(lat) < 1e-6 and abs(lon) < 1e-6`, y rechaza un punto si la velocidad implícita respecto al siguiente válido más reciente supera 70 m/s.
  - `CarStatus(state: Literal["moving", "parked", "no_data"], last_ts: int | None, point: GpsPoint | None, speed_kmh: float | None)`.
  - `car_status(conn, now_ms: int) -> CarStatus`: último dato = `MAX(ts)` de `records`; puntos = los 50 `gps` más recientes por `ts`; `moving` si `now_ms - last_ts < 300000`. `speed_kmh` sale del último `obd.speed_kmh` de los 60 s anteriores a `last_ts` o, si no hay, de `speed_mps * 3.6` del punto.
  - `format_status(status: CarStatus, now_ms: int, tz: str) -> str`, con estos textos exactos:
    - En marcha: `🚗 En marcha · último dato hace {rel} · {v} km/h` (sin ` · {v} km/h` si no hay velocidad).
    - Aparcado: `🅿️ Aparcado desde las {HH:MM} (hace {rel})`, más `\nÚltima posición GPS de las {HH:MM}` si `last_ts - point.ts > 120000`.
    - Sin punto válido: añade `\nSin posición GPS todavía.`
    - Sin datos: `Todavía no hay datos del coche.`
    - `rel`: `N s` si es menos de 1 min, `N min` si es menos de 1 h, `N h M min` en el resto.

- [ ] **Step 1: Tests que fallan:**
  - `test_skips_zero_zero`, `test_skips_low_accuracy` y `test_skips_impossible_jump` (dos puntos a 10 km en 10 s);
  - `test_moving_when_recent` (4 min 59 s → `moving`) y `test_parked_after_five_minutes` (5 min → `parked`);
  - `test_no_data`;
  - `test_status_without_valid_gps` (Review Focus 3);
  - `test_format_parked_with_gps_gap`, comprobando `"🅿️ Aparcado desde las 18:42 (hace 2 h 5 min)\nÚltima posición GPS de las 18:39"` con reloj fijo en Europe/Madrid;
  - `test_format_moving` y `test_relative_time_buckets`.
- [ ] **Step 2:** Ejecutar. Esperado: FAIL.
- [ ] **Step 3:** Implementar `location.py` con `zoneinfo` y la distancia haversine.
- [ ] **Step 4:** Ejecutar. Esperado: PASS.
- [ ] **Step 5:** Commit en `feat/bot-donde`: `feat: ✨ add car status logic for /donde`.

### Task 6: Bot de Telegram

**Files:**
- Create: `server/app/bot/__init__.py`, `server/app/bot/telegram.py`, `server/app/bot/commands.py`, `server/app/bot/__main__.py`
- Test: `server/tests/test_bot.py`

**Interfaces:**
- Consumes: `car_status` y `format_status` de la tarea 5, y `Settings`.
- Produces:
  - `telegram.TelegramClient(token: str, http: httpx.Client)` con `get_updates(offset: int | None, timeout: int = 50) -> list[dict]`, `send_message(chat_id, text)`, `send_location(chat_id, lat, lon)` y `set_my_commands(list[tuple[str, str]])`.
  - `commands.handle_update(update: dict, *, chat_id: int, client, conn, now_ms: int, tz: str) -> None`: solo procesa `update["message"]` con `text` y `chat.id == chat_id`. `/donde` envía primero el texto y después la ubicación si hay punto. `/start` envía `"Comandos:\n/donde · dónde está el coche"`. Cualquier otra cosa se ignora.
  - `bot.__main__`: bucle con `offset = último update_id + 1`. Ante `httpx.HTTPError` o una respuesta `ok: false`, espera 1, 2, 4… hasta 60 s y sigue. Un fallo dentro de `handle_update` se registra y no detiene el bucle. Termina con error si falta el token o `CHAT_ID`.

- [ ] **Step 1: Tests que fallan**, con un cliente falso que guarda las llamadas:
  - `test_donde_sends_text_then_location`;
  - `test_donde_without_point_sends_only_text`;
  - `test_other_chat_is_ignored`;
  - `test_non_text_updates_are_ignored` (parametrizado: `edited_message`, `callback_query`, un mensaje con foto sin `text` y un `message` sin `chat`; Review Focus 4);
  - `test_start_lists_commands`;
  - `test_client_builds_urls` (con `httpx.MockTransport`: `getUpdates` con `offset` y `timeout`, y `sendLocation` con `latitude` y `longitude`).
- [ ] **Step 2:** Ejecutar. Esperado: FAIL.
- [ ] **Step 3:** Implementar los tres módulos. Al arrancar, `set_my_commands([("donde", "Dónde está el coche")])`. El cliente HTTP usa un timeout de lectura de 60 s.
- [ ] **Step 4:** Ejecutar. Esperado: PASS.
- [ ] **Step 5:** Commit: `feat: ✨ add car-trace telegram bot with /donde`. Integrar `feat/bot-donde` en `develop`.

### Task 7: Simulador de trayecto

**Files:**
- Create: `tools/simulate_drive.py` (solo biblioteca estándar, Python ≥ 3.9 para que funcione también en lnk-server)
- Test: `server/tests/test_simulator.py`

**Interfaces:**
- Consumes: el contrato (tarea 1).
- Produces: la CLI `python3 tools/simulate_drive.py --url URL --token TOKEN [--minutes 10] [--batch 100] [--ago-min 0] [--repeat]`. Genera una sesión con `session_start`, un `dtc` vacío, `gps` y `obd` cada 3 s por una ruta en línea recta (unos 50 km/h) que termina `--ago-min` minutos antes de ahora, y la envía por lotes. Imprime el JSON de cada respuesta. Con `--repeat`, reenvía el último lote. Si alguna respuesta no es `200`, termina con código 1.

- [ ] **Step 1: Test que falla**: `test_simulator_against_app` levanta `create_app` con uvicorn en un hilo, en un puerto libre, ejecuta el simulador con `--minutes 2 --repeat` y comprueba el código de salida 0, `accepted` = 2 × 40 + 2 = 82 en total y el último lote todo `duplicates`.
- [ ] **Step 2:** Ejecutar. Esperado: FAIL.
- [ ] **Step 3:** Implementar con `urllib.request`, `uuid` y `json`.
- [ ] **Step 4:** Ejecutar. Esperado: PASS.
- [ ] **Step 5:** Commit en `feat/simulator`: `feat: ✨ add drive simulator tool`. Integrar en `develop`.

### Task 8: Imagen, compose y prueba local con contenedores

**Files:**
- Create: `server/Dockerfile`, `server/.dockerignore`, `docker-compose.yml` (raíz), `.env.example` (raíz)

**Interfaces:**
- Consumes: `python -m app` (tarea 4) y `python -m app.bot` (tarea 6).
- Produces: los servicios `api` (`car-trace-api`) y `bot` (`car-trace-bot`), que el despliegue (tarea 9) usa tal cual.

- [ ] **Step 1:** El `Dockerfile` parte de `python:3.12-slim`, copia el binario `uv` desde `ghcr.io/astral-sh/uv` (comprobar la etiqueta actual con Context7), hace `uv sync --frozen --no-dev`, crea un usuario sin root y define `CMD ["python", "-m", "app"]`.
- [ ] **Step 2:** El `docker-compose.yml` tiene:
  - `api`: `build: ./server`, `container_name: car-trace-api`, `ports: ["127.0.0.1:8090:8000", "<TAILSCALE_IP>:8090:8000"]`, `environment: {CAR_TRACE_INGEST_TOKEN: ${CAR_TRACE_INGEST_TOKEN}, CAR_TRACE_DB: /data/car-trace.db}`, `volumes: ["./data:/data:Z"]` y `restart: unless-stopped`.
  - `bot`: la misma imagen, `command: ["python", "-m", "app.bot"]`, `container_name: car-trace-bot`, `environment` solo con `CAR_TRACE_BOT_TOKEN`, `CHAT_ID`, `CAR_TRACE_DB` y `CAR_TRACE_TZ`, el mismo volumen y sin puertos.
  - `.env.example` lista esas variables vacías.
- [ ] **Step 3:** Prueba local en WSL. Crear un `.env` temporal con un token de prueba y la IP de los puertos cambiada a `127.0.0.1` mediante un `docker-compose.override.yml` local (en `.gitignore`). Después `podman compose up -d --build api` y `python3 tools/simulate_drive.py --url http://127.0.0.1:8090/api/v1/ingest --token <prueba> --minutes 1`. Esperado: salida 0. Si `podman compose` no tiene proveedor, construir con `podman build` y ejecutar con `podman run`.
- [ ] **Step 4:** Ejecutar `podman compose down` y borrar `data/`, `.env` y el override locales.
- [ ] **Step 5:** Commit en `feat/container`: `chore: 🔧 add container image and compose services`. Integrar en `develop`.

### Task 9: Despliegue en lnk-server y validación del paso 1

Necesita a Víctor (remoto de GitHub, `sudo`, Telegram). Lo ejecuta la sesión principal, no un subagente.

**Files:**
- Modify (en lnk-server, repo `server-apps`, con su gitflow y el stash de tracked si `develop` sigue con cambios sin commitear): `conf/available-server-apps.conf` (`car-trace=True`) y `conf/ports.conf` (`car-trace = 8090:8000 ; ingest via Funnel, Tailscale only`)
- Create (brain): `projects/car-trace/car-trace.md`; Modify: `infra/ports.md`

- [ ] **Step 1:** Añadir el remoto de GitHub y hacer push de `main` y `develop`. Clonar en `~/server-apps/apps/car-trace` (rama `main` tras la primera release; hasta entonces, `develop`).
- [ ] **Step 2:** En el servidor, añadir `CAR_TRACE_INGEST_TOKEN` a `~/server-apps/.env` con `python3 -c 'import secrets;print(secrets.token_urlsafe(32))'`, sin mostrarlo en la salida, y crear `ln -s ../../.env ~/server-apps/apps/car-trace/.env`.
- [ ] **Step 3:** Ejecutar `podman-compose up -d --build` en `apps/car-trace`. Comprobar `curl -s http://<TAILSCALE_IP>:8090/healthz` → `{"ok":true}` y, desde la LAN, `curl -m 3 http://<LAN_IP>:8090/healthz` → error de conexión.
- [ ] **Step 4:** Víctor ejecuta `sudo tailscale funnel --bg --set-path /api/v1/ingest http://127.0.0.1:8090/api/v1/ingest`. Comprobar con `tailscale funnel status` y `curl` cómo trata `--set-path` la ruta de destino. Si la duplica (`/api/v1/ingest/api/v1/ingest`), el destino pasa a ser `http://127.0.0.1:8090`.
- [ ] **Step 5:** Validación del paso 1 (spec 8.2), desde fuera del tailnet o con la URL pública:
  - `simulate_drive.py --url https://<servidor>.<tailnet>.ts.net/api/v1/ingest --token … --ago-min 6 --repeat` → salida 0 y el último lote todo `duplicates`;
  - token incorrecto → `401`;
  - `https://<servidor>.<tailnet>.ts.net/healthz` → `404`;
  - Víctor manda `/start` y `/donde` al bot → chincheta y "🅿️ Aparcado desde…".
- [ ] **Step 6:** Ejecutar `systemctl --user restart server-apps.service` y comprobar que `car-trace-api` y `car-trace-bot` siguen arriba (`podman ps`).
- [ ] **Step 7:** Escribir la ficha del brain (`type: project`, `status: active`, `machine: "[[lnk-server]]"`, `repo`, `ports: [{port: 8090, service: "car-trace api (Funnel only /api/v1/ingest)", host: lnk-server}]`, `stack`, `verified`) y actualizar `infra/ports.md`. Borrar los datos simulados: `DELETE FROM records` en `data/car-trace.db` antes del uso real.
