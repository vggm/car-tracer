# Bloque 1 · Cadena tablet → lnk-server con `/donde`

Fecha: 2026-11-18 · Estado: pendiente de revisión

Spec del primer bloque de Telemetría 307. Desarrolla lo decidido en `docs/01` a `docs/05` y concreta las fases 1 a 4 de la hoja de ruta (app mínima, GPS y cola, recepción en el servidor, bot con `/donde`). El panel web, los trayectos calculados, las alertas y el mantenimiento quedan para bloques posteriores.

## 1. Objetivo y criterio de éxito

La app de la tablet Junsun arranca sola al encender el coche, lee el GPS y el ELM327, guarda todo en una cola local y lo envía a lnk-server por Tailscale Funnel. El servidor lo guarda sin duplicados y un bot de Telegram propio responde a `/donde` con la posición del coche y si está en marcha o aparcado.

El bloque está terminado cuando se cumplen las tres validaciones de la sección 8.

## 2. Decisiones tomadas

| Decisión | Motivo |
| --- | --- |
| Un solo repo con `server/` y `android/`; remoto en GitHub (lo facilita Víctor) | El contrato vive junto a sus dos consumidores |
| Orden de trabajo "C": contrato → servidor y bot en paralelo con el esqueleto de la app → ELM327 y GPS reales | El riesgo real es que la Junsun mantenga viva la app; se prueba pronto y sin depender del coche |
| Bot de Telegram propio (`CAR_TRACE_BOT_TOKEN`), separado del bot de la biblioteca | Un token solo admite un proceso haciendo long polling; los proyectos quedan independientes |
| `CHAT_ID` compartido con el bot de la biblioteca | En un chat privado el `chat_id` es el ID del usuario, igual con cualquier bot |
| SQLite en lugar de PostgreSQL | ~2.000 registros por hora de conducción; lnk-server tiene ~2,6 GB de RAM libres |
| `/donde` se calcula al consultar, sin procesos en segundo plano | Basta con el último dato; los procesos de fondo llegarán con las alertas |
| SDK de Android por línea de comandos en WSL | Los agentes compilan y prueban sin Android Studio |

## 3. Arquitectura

```
Tablet Junsun                                  lnk-server (podman rootless)
┌──────────────────────────────┐              ┌────────────────────────────────────┐
│ BootReceiver → TelemetrySvc  │              │ tailscale funnel :443              │
│   GpsSource ─┐               │  HTTPS       │   /api/v1/ingest ─► 127.0.0.1:8090 │
│   ObdSource ─┼─► Queue (Room)│──Bearer────► │                                    │
│   SessionClock┘     │        │  (Funnel)    │  car-trace-api  (FastAPI) ─┐       │
│                 Uploader     │              │  car-trace-bot  (polling) ─┼► SQLite│
└──────────────────────────────┘              └────────────────────────────┼───────┘
                                                                Telegram ◄─┘ (saliente)
```

## 4. Contrato de datos (v1)

Es la pieza que comparten app y servidor. Se documenta en `docs/contract/ingest-v1.md` y se acompaña de ejemplos en `docs/contract/examples/` (lotes válidos e inválidos con la respuesta esperada). **Los tests del servidor y los de la app usan esos mismos ficheros.**

### 4.1 Petición

`POST /api/v1/ingest`, cabeceras `Authorization: Bearer <CAR_TRACE_INGEST_TOKEN>` y `Content-Type: application/json`. Cuerpo como máximo de 256 KB y 500 registros.

```json
{
  "device_id": "junsun-307",
  "app_version": "0.1.0",
  "records": [
    {"id": "1f0c…", "session_id": "9a2b…", "seq": 41, "ts": 1763481600123, "type": "gps",
     "lat": 40.4702, "lon": -3.7722, "acc_m": 6.0, "speed_mps": 13.2, "bearing": 270.0, "alt_m": 410.0},
    {"id": "1f0d…", "session_id": "9a2b…", "seq": 42, "ts": 1763481600500, "type": "obd",
     "values": {"rpm": 1850, "speed_kmh": 47, "coolant_c": 88, "intake_kpa": 140, "load_pct": 42}},
    {"id": "1f0e…", "session_id": "9a2b…", "seq": 1, "ts": 1763481500000, "type": "dtc",
     "active": ["P0401"], "pending": []},
    {"id": "1f0f…", "session_id": "9a2b…", "seq": 0, "ts": 1763481499000, "type": "event",
     "event": "session_start"}
  ]
}
```

### 4.2 Campos

Campos comunes a todo registro:

| Campo | Regla |
| --- | --- |
| `id` | UUID (texto) generado en la tablet. Clave de idempotencia |
| `session_id` | UUID. Nuevo en cada arranque del servicio y en cada vuelta de suspensión |
| `seq` | Entero ≥ 0, creciente dentro de la sesión |
| `ts` | Milisegundos UTC. Válido entre 2024-01-01 y ahora + 5 min |
| `type` | `gps`, `obd`, `dtc` o `event` |

Campos por tipo:

| Tipo | Campos |
| --- | --- |
| `gps` | `lat` [-90, 90], `lon` [-180, 180], `acc_m` ≥ 0 obligatorios; `speed_mps` ≥ 0, `bearing` [0, 360), `alt_m` opcionales |
| `obd` | `values`: objeto no vacío, claves `^[a-z0-9_]{1,32}$`, valores numéricos. Claves conocidas: `rpm`, `speed_kmh`, `coolant_c`, `intake_kpa`, `load_pct`, `throttle_pct`, `voltage_v`, `fuel_rate_lph`. Las desconocidas se aceptan y se guardan (compatibilidad hacia delante) |
| `dtc` | `active` y `pending`: listas de códigos `^[PCBU][0-9A-F]{4}$` (pueden estar vacías) |
| `event` | `event` ∈ {`session_start`, `resumed`, `obd_connected`, `obd_lost`, `obd_error`}; `detail` opcional, ≤ 200 caracteres |

`device_id` sigue `^[a-z0-9-]{1,64}$`; `app_version` es texto de ≤ 32 caracteres.

### 4.3 Respuestas y qué hace la app

| Respuesta | Significado | La app |
| --- | --- | --- |
| `200` `{"accepted": n, "duplicates": n, "rejected": [{"index": i, "id": "…", "error": "…"}]}` | Lote procesado; cada registro se valida por separado | Borra el lote entero de la cola |
| `400` | El lote en sí es inválido (JSON roto, faltan `device_id` o `records`, más de 500 registros) | Lo descarta y lo anota en el registro de errores: nunca tendrá éxito |
| `401` | Token ausente o incorrecto | Conserva el lote y muestra el error en la pantalla de estado y en la notificación |
| `413` | Más de 256 KB | Parte el lote por la mitad y reintenta |
| `5xx` o sin red | Fallo temporal | Reintenta con espera creciente (30 s → 10 min) |

Un duplicado (mismo `id` ya guardado) cuenta en `duplicates` y no modifica lo guardado.

## 5. Servidor

### 5.1 Estructura

```
docker-compose.yml          # en la raíz: el repo se clona como ~/server-apps/apps/car-trace
server/
  Dockerfile  pyproject.toml (uv)
  app/
    config.py               # variables de entorno
    db.py                   # conexión SQLite (WAL, busy_timeout) y esquema
    contract.py             # modelos pydantic del contrato v1
    ingest.py               # router POST /api/v1/ingest
    funnel_guard.py         # middleware: lo que llega por Funnel solo puede ir a /api/v1/ingest
    location.py             # último punto GPS válido y estado en marcha/aparcado
    main.py                 # app FastAPI
    bot/
      telegram.py           # cliente mínimo con httpx (getUpdates, sendMessage, sendLocation)
      commands.py           # /start, /donde
      __main__.py           # bucle de long polling
  tests/
tools/simulate_drive.py     # imita la tablet: envía un trayecto falso a cualquier URL
```

### 5.2 Base de datos

SQLite en `/data/car-trace.db` (volumen `./data`), en modo WAL y con `busy_timeout`, porque `api` escribe y `bot` lee. Una tabla:

```sql
CREATE TABLE records (
  id          TEXT PRIMARY KEY,
  device_id   TEXT NOT NULL,
  session_id  TEXT NOT NULL,
  seq         INTEGER NOT NULL,
  ts          INTEGER NOT NULL,      -- ms UTC
  type        TEXT NOT NULL,
  data        TEXT NOT NULL,         -- JSON con los campos propios del tipo
  received_at INTEGER NOT NULL
);
CREATE INDEX records_type_ts ON records(type, ts);
CREATE INDEX records_session ON records(session_id, seq);
```

La inserción usa `INSERT OR IGNORE`: si no se inserta ninguna fila, el registro cuenta como duplicado. El esquema se crea al arrancar si no existe; una tabla `schema_version` deja preparadas las migraciones futuras.

### 5.3 Exposición y seguridad

- `api` publica el puerto 8090 solo en `127.0.0.1` (para Funnel) y en `<TAILSCALE_IP>` (panel futuro por Tailscale), nunca en la LAN.
- Funnel: `sudo tailscale funnel --bg --set-path /api/v1/ingest http://127.0.0.1:8090/api/v1/ingest`. Lo ejecuta Víctor, porque `tailscale` no tiene operador configurado. En el plan se comprobará cómo trata `--set-path` la ruta de destino.
- `funnel_guard`: toda petición que llega por Tailscale serve o Funnel trae `X-Forwarded-Host`. Si la lleva y la ruta no es `/api/v1/ingest`, se responde `404`. Así nada más queda expuesto aunque Funnel se configure mal.
- El token se compara con `hmac.compare_digest`. Se rechaza un `Content-Length` > 256 KB antes de leer el cuerpo, y también un cuerpo que supere ese límite al leerlo.
- No hay documentación automática (`/docs`, `/openapi.json`) en producción.

### 5.4 Secretos y despliegue

- Los secretos están en `~/server-apps/.env`: `CAR_TRACE_BOT_TOKEN` (ya creado), `CHAT_ID` (ya existe) y `CAR_TRACE_INGEST_TOKEN`, que se generará con `secrets.token_urlsafe(32)` directamente en el servidor.
- En el servidor, `apps/car-trace/.env` es un enlace simbólico a `../../.env`. `podman-compose` lo usa solo para interpolar variables, y cada contenedor recibe únicamente las suyas (`api` el token de recepción; `bot` el token del bot y `CHAT_ID`). El contenedor expuesto a internet no ve el resto de secretos del servidor.
- Despliegue: clonar el repo en `~/server-apps/apps/car-trace`, crear el enlace `.env`, añadir `car-trace=True` a `conf/available-server-apps.conf` y `car-trace = 8090:8000` a `conf/ports.conf` (cambios en `server-apps` con su gitflow), y ejecutar `podman-compose up -d --build`. Para actualizar: `git pull` y el mismo comando.
- Brain: ficha `projects/car-trace/car-trace.md` (puerto 8090, URL de Funnel, dónde están los secretos) y actualización de `infra/ports.md`.

### 5.5 `/donde`

Lógica pura en `location.py` (recibe la hora actual como parámetro para poder probarla):

1. **Último dato**: el registro con mayor `ts`, de cualquier tipo.
2. **Último punto válido**: se recorren los ~50 puntos `gps` más recientes, del más nuevo al más viejo, y se toma el primero que cumpla: `acc_m` ≤ 50, no está en (0, 0) y la velocidad implícita respecto al punto válido anterior es ≤ 70 m/s (unos 250 km/h).
3. **Estado**: si el último dato tiene menos de 5 minutos, "en marcha"; si no, "aparcado".

Respuesta del bot (horas en Europe/Madrid):

- En marcha: `🚗 En marcha · último dato hace 20 s · 47 km/h` y la ubicación (`sendLocation`).
- Aparcado: `🅿️ Aparcado desde las 18:42 (hace 2 h 5 min)` y la ubicación. Si el último punto válido es más de 2 minutos anterior al último dato (por ejemplo, un parking subterráneo), se añade `Última posición GPS de las 18:39`.
- Sin datos: `Todavía no hay datos del coche.`

El bot ignora los mensajes de cualquier chat que no sea `CHAT_ID`. `/start` responde con la lista de comandos. Al arrancar sincroniza el menú con `setMyCommands`. Si Telegram falla, reintenta con espera creciente y nunca termina el proceso.

## 6. App Android

### 6.1 Base

Kotlin, `minSdk 33`, `targetSdk 34`, Gradle (KTS) con version catalog; las versiones exactas se fijan en el plan consultando la documentación. Paquete `dev.lnk.cartrace`. Sin Google Play Services. Librerías: coroutines, Room, OkHttp y kotlinx.serialization. La interfaz con Jetpack Compose.

### 6.2 Piezas

| Pieza | Responsabilidad |
| --- | --- |
| `BootReceiver` | Arranca `TelemetryService` con `BOOT_COMPLETED`, `QUICKBOOT_POWERON` y `MY_PACKAGE_REPLACED`. Las señales de encendido propias de la Junsun se investigan en la tablet durante el paso 2 |
| `TelemetryService` | Servicio en primer plano de tipos `location` y `connectedDevice` con notificación fija. Arranca y supervisa las fuentes y el `Uploader`, y gestiona las sesiones |
| `GpsSource` | `LocationManager.GPS_PROVIDER` cada ~3 s; emite registros `gps` |
| `ObdSource` | Bluetooth clásico, socket RFCOMM/SPP con el adaptador elegido. Inicialización: `ATZ`, `ATE0`, `ATL0`, `ATS0`, `ATH0`, `ATSP0`; guarda el protocolo detectado (`ATDPN`) para arrancar antes la próxima vez. Al empezar la sesión lee los PIDs soportados (`0100`, `0120`, `0140`) y las averías (`03` y `07`, un registro `dtc`). En bucle lee `010C`, `010D`, `0105`, `010B` y `0104` (`015E` si está soportado), y emite un registro `obd` cada ~3 s con los últimos valores. `ATRV` (voltaje) cada 60 s. Si pierde la conexión, emite `obd_lost` y reintenta con espera creciente (5 s → 2 min) |
| `ElmParser` | Funciones puras que convierten las respuestas del ELM327 en valores, averías y PIDs soportados. Tolera `SEARCHING...`, `NO DATA`, `STOPPED` y respuestas en varias líneas |
| `SessionClock` | Ver 6.3 |
| `Queue` | Room: tabla `pending_records`. Se escribe al momento. Tope de 200.000 filas: si se supera, borra las más antiguas |
| `Uploader` | Cada ~30 s, si hay red, toma hasta 500 registros con `ts` resuelto (los más antiguos primero), los envía y actúa según la tabla 4.3 |
| `SimulatedSources` | `FakeGps` (recorre una ruta grabada) y `FakeElm` (responde como un ELM327 con valores verosímiles). Se activan con el modo simulado de Ajustes |
| `SleepDetector` | Cada 5 s compara cuánto avanzan `elapsedRealtime()` (cuenta también el tiempo dormido) y `uptimeMillis()` (no lo cuenta). Si la diferencia crece más de 60 s, la tablet ha dormido: emite `resumed`, abre sesión nueva y reconecta el adaptador |

Cada fuente funciona en su propia corrutina con supervisión: un fallo en una no detiene las demás ni el servicio.

### 6.3 Hora de los registros

Cada registro guarda al crearse `boot_count` (`Settings.Global.BOOT_COUNT`), `elapsed_ms` (`elapsedRealtime`) y `wall_ms` (la hora del sistema en ese momento). Su `ts` se resuelve así, por orden:

1. **GPS**: el primer fix de ese arranque fija `offset = location.time − elapsedRealtime` para ese `boot_count`, y `ts = elapsed_ms + offset`.
2. **Hora del sistema**: si no hay offset de GPS, se usa `wall_ms`, siempre que no sea anterior a la fecha de compilación de la app.
3. **Ninguna**: el registro espera en la cola. Si pertenece a un arranque anterior que nunca tuvo hora fiable, se descarta y se cuenta en el estado.

### 6.4 Pantallas

- **Estado**: servicio activo o no, adaptador (conectado, reintentando o error), último GPS (hora y precisión), registros pendientes, último envío (hora y resultado) y errores recientes.
- **Ajustes**: URL del servidor, token, adaptador (lista de dispositivos emparejados) y modo simulado.
- **Primera vez**: pide permisos en orden (ubicación precisa, después "Permitir siempre", Bluetooth `CONNECT`, suficiente para usar adaptadores ya emparejados, y notificaciones), pide excluir la app del ahorro de batería y muestra cómo añadirla al autoarranque de la Junsun.

### 6.5 Compilación e instalación

Se instalan en WSL el JDK 17 y las herramientas de línea de comandos del SDK de Android. `./gradlew test assembleRelease` compila y pasa los tests. El APK se firma con un keystore propio guardado fuera del repo, para que las actualizaciones se instalen encima. Víctor lo instala en la tablet con un pendrive o con `adb` por wifi.

## 7. Errores y límites (resumen)

| Situación | Comportamiento |
| --- | --- |
| Un registro inválido | Se rechaza solo ese; el resto del lote se guarda |
| Lote reenviado | Todo cuenta como duplicado; nada cambia |
| Hora absurda | La app no la envía (6.3); el servidor la rechaza (4.2) |
| Sin cobertura o servidor caído | La cola guarda hasta 200.000 registros y se vacía después, empezando por lo más antiguo |
| ELM327 ausente o la ECU no responde | Sigue el GPS; el OBD reintenta con espera creciente |
| La tablet duerme | `SleepDetector` abre sesión nueva al despertar |
| Token incorrecto | `401`; la app conserva los datos y lo muestra |
| Alguien prueba la URL pública | Sin token: `401`; cualquier otra ruta: `404` |

## 8. Pruebas y validación

### 8.1 Automáticas

- **Ejemplos del contrato** (`docs/contract/examples/`): lotes JSON con la respuesta esperada. El servidor comprueba que los procesa como se espera; la app, que serializa registros con la misma forma que los ejemplos válidos.
- **Servidor (pytest)**:
  - ingesta: aceptados, duplicados, rechazo parcial, `400`, `401`, `413` y límites de `ts`;
  - `funnel_guard`;
  - `location.py` con reloj fijo: en marcha, aparcado, sin GPS al aparcar, puntos (0,0), baja precisión y saltos imposibles;
  - comandos del bot con un cliente de Telegram simulado, incluido ignorar otros chats.
- **App (tests JVM)**: `ElmParser` con respuestas reales y erróneas, `SessionClock`, `SleepDetector` con relojes falsos, `Uploader` frente a cada respuesta de la tabla 4.3 (con MockWebServer) y el tope de la `Queue`.
- **Simulador** `tools/simulate_drive.py --url … --token …`: envía un trayecto realista por lotes; con `--repeat`, reenvía el último lote.

### 8.2 Validación por pasos

| Paso | Se da por bueno cuando… |
| --- | --- |
| 1. Servidor y bot | Con el simulador contra la URL pública de Funnel, el trayecto queda guardado; al reenviarlo, todo es `duplicates`; un token incorrecto da `401`; otra ruta da `404`. En Telegram, `/donde` muestra la ubicación y "Aparcado desde…" pasados 5 minutos |
| 2. App en modo simulado | Instalada en la Junsun: tras quitar y poner el contacto sin tocar la tablet, la app arranca sola, los datos llegan y `/donde` los refleja; tras una suspensión aparece una sesión nueva; la navegación y la música no se ven afectadas |
| 3. ELM327 y GPS reales | 30 minutos conduciendo sin cortes y las RPM cuadran con el cuentarrevoluciones. Al salir de un parking subterráneo, los datos llegan. Las averías coinciden con las que lee Car Scanner. `/donde` encuentra el coche aparcado |

## 9. Fuera de este bloque

Panel web, cálculo de trayectos, alertas (averías, voltaje, temperatura), kilometraje y mantenimiento, bus CAN de confort, borrar averías y app móvil propia. Las copias de seguridad de `data/` también quedan fuera; se decidirán con el panel.

## 10. Lo que necesita Víctor

1. El remoto de GitHub para el repo.
2. Ejecutar una vez el comando de Funnel con `sudo` (sección 5.3).
3. Escribir en la app la URL y el token de recepción.
4. Mandar `/start` al bot nuevo una vez.
5. Instalar el APK en la Junsun, conceder permisos y añadir la app al autoarranque.
