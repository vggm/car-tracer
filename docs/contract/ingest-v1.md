# Contrato de ingesta v1

Interfaz única entre la app Android (tablet en el coche) y el servidor FastAPI. Los ejemplos compartidos están en `docs/contract/examples/` y los usan los tests de ambos lados.

## 4.1 Petición

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

## 4.2 Campos

Campos comunes a todo registro:

| Campo | Regla |
| --- | --- |
| `id` | UUID (texto) generado en la tablet. Clave de idempotencia |
| `session_id` | UUID. Nuevo en cada arranque del servicio y en cada vuelta de suspensión |
| `seq` | Entero ≥ 0, creciente dentro de la sesión |
| `ts` | Milisegundos UTC. Válido entre 2024-01-01 y ahora + 5 min |
| `type` | `gps`, `obd`, `dtc`, `event` o `health` |

Campos por tipo:

| Tipo | Campos |
| --- | --- |
| `gps` | `lat` [-90, 90], `lon` [-180, 180], `acc_m` ≥ 0 obligatorios; `speed_mps` ≥ 0, `bearing` [0, 360), `alt_m` opcionales |
| `obd` | `values`: objeto no vacío, claves `^[a-z0-9_]{1,32}$`, valores numéricos. Claves conocidas: `rpm`, `speed_kmh`, `coolant_c`, `intake_kpa`, `load_pct`, `throttle_pct`, `voltage_v`, `fuel_rate_lph`. Las desconocidas se aceptan y se guardan (compatibilidad hacia delante) |
| `dtc` | `active` y `pending`: listas de códigos `^[PCBU][0-9A-F]{4}$` (pueden estar vacías) |
| `event` | `event` ∈ {`session_start`, `resumed`, `obd_connected`, `obd_lost`, `obd_error`, `obd_attempt_failed`, `dtc_scan`, `dtc_scan_failed`, `dtc_clear`, `dtc_clear_failed`, `obd_trace`, `diag`}; `detail` opcional, ≤ 200 caracteres (≤ 4000 para `obd_trace`, ≤ 500 para `diag`). `obd_trace`: traza en bruto de la conexión OBD (cabecera `attempt n=<n> variant=<Vx> result=<ok\|fail> session_age=<s>s` o `lost`, seguida de líneas `+<ms> > <cmd> \| <respuesta> \| <ms>[ \| ERR <motivo>]`). `diag`: diagnóstico general, `detail = "<componente>.<código> [xN] <texto>"`. Ninguno lleva MAC, coordenadas, URLs con token ni rutas de usuario. `obd_connected`: `detail` puede llevar tras el protocolo ` n=<intento> t=<s>s`. `obd_attempt_failed` (un intento de conexión OBD fallido): `detail = "n=<intento> t=<s>s v=<voltaje> | <parte> | ..."`, con una parte por fase o protocolo probado (`open: <mensaje>` o `<protocolo>: <motivo>`), cada una ≤ 60 caracteres y `v=?` si no se pudo leer. `dtc_scan`: `detail = "<id>"` de la petición atendida; `dtc_scan_failed`: `detail = "<id> <reason>"`, con `reason` ∈ {`obd_not_connected` (sin OBD conectado), `obd_error` (el adaptador respondió con error o se perdió el enlace durante la lectura)}. `dtc_clear`: `detail = "<id>"` de la petición de borrado atendida; `dtc_clear_failed`: `detail = "<id> <reason>"`, con `reason` ∈ {`obd_not_connected` (sin OBD conectado), `engine_running` (motor en marcha), `rejected` (la centralita no aceptó el borrado), `obd_error` (se perdió el enlace durante el borrado)} |
| `health` | `values`: objeto no vacío, claves `^[a-z0-9_]{1,32}$`, valores numéricos (latido de salud de la app). No afecta a trayectos, avisos ni al bot, que filtran por tipo |

`device_id` sigue `^[a-z0-9-]{1,64}$`; `app_version` es texto de ≤ 32 caracteres.

## 4.3 Respuestas y qué hace la app

| Respuesta | Significado | La app |
| --- | --- | --- |
| `200` `{"accepted": n, "duplicates": n, "rejected": [{"index": i, "id": "…", "error": "…"}], "commands": [{"type": "read_dtc" o "clear_dtc", "id": "<uuid>"}]}` | Lote procesado; cada registro se valida por separado. `commands` siempre está presente (puede ser `[]`) y lista las peticiones abiertas (`read_dtc`: leer averías; `clear_dtc`: borrar las averías de la centralita, solo con el motor apagado) de menos de 90 s, que se reenvían en cada respuesta hasta que llega el resultado o caducan | Borra el lote entero de la cola y atiende los `commands` nuevos (ignora ids ya atendidos) |
| `400` | El lote en sí es inválido (JSON roto, faltan `device_id` o `records`, más de 500 registros) | Lo descarta y lo anota en el registro de errores: nunca tendrá éxito |
| `401` | Token ausente o incorrecto | Conserva el lote y muestra el error en la pantalla de estado y en la notificación |
| `413` | Más de 256 KB | Parte el lote por la mitad y reintenta |
| `5xx` o sin red | Fallo temporal | Reintenta con espera creciente (30 s → 10 min) |

Los eventos `obd_trace` y `diag` y el tipo `health` (app 0.1.7) requieren el servidor nuevo: uno anterior los rechazaría como desconocidos, así que el servidor se despliega primero. Las apps 0.1.6 siguen funcionando con el servidor nuevo.

Compatibilidad: una app antigua ignora el campo `commands` y los tipos de orden que no conoce. El servidor debe desplegarse antes que una app que envíe los eventos `dtc_scan` / `dtc_scan_failed` / `dtc_clear` / `dtc_clear_failed`, porque un servidor anterior los rechazaría como evento desconocido.

Un duplicado (mismo `id` ya guardado) cuenta en `duplicates` y no modifica lo guardado.

## Versionado

Cualquier cambio incompatible crea `/api/v2/ingest`; `/api/v1/ingest` se mantiene tal cual. Los cambios compatibles (p. ej. nuevas claves `obd` desconocidas) no requieren versión nueva.
