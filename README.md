# Telemetría 307

Telemetría casera para un Peugeot 307: saber dónde está el coche, guardar el histórico de trayectos y detectar a tiempo problemas mecánicos. Usa la tablet Android que ya lleva el coche, un adaptador OBD2 ELM327 y un servidor propio en casa, sin servicios de pago.

## Cómo funciona

```
Tablet Junsun (Android)                       Servidor de casa (Podman)
┌─────────────────────────────┐   HTTPS       ┌──────────────────────────┐
│ App Telemetría 307          │   Tailscale   │ car-trace-api (FastAPI)  │
│  · GPS de la tablet         │ ── Funnel ──▶ │  POST /api/v1/ingest     │
│  · ELM327 por Bluetooth     │   + token     │        │                 │
│  · cola local (Room)        │               │     SQLite               │
└─────────────────────────────┘               │        │                 │
                                              │ car-trace-bot ◀──────────┼── Telegram (/donde)
                                              └──────────────────────────┘
```

1. La app arranca sola al encender el coche y trabaja en segundo plano como servicio en primer plano.
2. Lee la posición GPS y los datos del motor (RPM, velocidad, temperatura, carga, averías) a través del ELM327.
3. Guarda cada lectura en una cola local y la envía por lotes al servidor. Si no hay cobertura, los datos esperan en la tablet y se envían después.
4. El servidor solo expone a Internet el punto de entrada de datos, mediante Tailscale Funnel y protegido con token. El resto queda dentro de la red privada.
5. Un bot de Telegram propio responde `/donde` con la última posición e indica si el coche está en marcha o aparcado.

## Estado

| Pieza | Estado |
| --- | --- |
| Contrato de datos tablet → servidor | Hecho ([`docs/contract/ingest-v1.md`](docs/contract/ingest-v1.md)) |
| Servidor de ingesta (FastAPI + SQLite) | Hecho y desplegado |
| Bot de Telegram con `/donde` | Hecho y desplegado |
| App Android (GPS, ELM327, cola, envío, arranque automático, modo simulado) | Hecha; en validación en la tablet |
| Prueba en el coche con el ELM327 real | Pendiente |
| Panel web con mapa, trayectos y gráficas | Pendiente |
| Alertas de averías, voltaje y mantenimiento | Pendiente |

## Estructura del repositorio

| Ruta | Contenido |
| --- | --- |
| `android/` | App Android en Kotlin con Jetpack Compose, Room, OkHttp y coroutines. minSdk 33, targetSdk 34 |
| `server/` | API de ingesta y bot de Telegram en Python 3.12 (FastAPI, pydantic, httpx), gestionado con uv |
| `docker-compose.yml` | Despliegue de los dos contenedores (`car-trace-api` y `car-trace-bot`) |
| `tools/simulate_drive.py` | Simula un trayecto y lo envía al servidor (solo stdlib) |
| `docs/` | Diseño, contrato de datos y guías |

## Puesta en marcha

### Servidor

Requiere Podman con `podman-compose` (o Docker Compose) y Tailscale.

```bash
cp .env.example .env    # rellena el token de ingesta, el del bot, el chat y la IP de Tailscale
podman-compose up -d --build
```

La API escucha en el puerto 8090 de `127.0.0.1` y de la IP de Tailscale, nunca en la LAN. Para que la tablet llegue desde Internet, publica solo la ruta de ingesta:

```bash
sudo tailscale funnel --bg --set-path /api/v1/ingest http://127.0.0.1:8090/api/v1/ingest
```

Un token de ingesta se puede generar con `python3 -c "import secrets; print(secrets.token_urlsafe(32))"`.

Tests:

```bash
cd server && uv run pytest
```

### App Android

```bash
cd android
./gradlew test assembleDebug
```

Instalación del entorno, firma del release e instalación en la tablet: [`docs/desarrollo-android.md`](docs/desarrollo-android.md) y [`docs/instalacion-tablet.md`](docs/instalacion-tablet.md).

### Probar sin coche

La app tiene un modo simulado que genera un trayecto ficticio. Desde un ordenador también se puede simular con:

```bash
CAR_TRACE_INGEST_TOKEN=<token> python3 tools/simulate_drive.py --url https://<servidor>/api/v1/ingest
```

## Documentación

| Documento | Contenido |
| --- | --- |
| [01 · Visión y alcance](docs/01-vision-y-alcance.md) | Objetivos, qué queda fuera y qué datos interesan |
| [02 · Hardware y vehículo](docs/02-hardware-y-vehiculo.md) | Peugeot 307, tablet Junsun, ELM327 y buses del coche |
| [03 · Arquitectura y decisiones](docs/03-arquitectura-y-decisiones.md) | Cómo encajan las piezas y por qué se eligió cada opción |
| [04 · Limitaciones y posibles soluciones](docs/04-limitaciones-y-soluciones.md) | Problemas conocidos o previsibles y cómo abordarlos |
| [05 · Hoja de ruta y preguntas abiertas](docs/05-hoja-de-ruta-y-preguntas.md) | Fases y lo que queda por decidir |
| [Contrato de ingesta v1](docs/contract/ingest-v1.md) | Formato de los lotes, validación y respuestas del servidor |
| [Desarrollo Android](docs/desarrollo-android.md) | Entorno, compilación y firma de la app |
| [Instalación en la tablet](docs/instalacion-tablet.md) | Instalar la app y validarla en modo simulado |
