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
| `type` | `gps`, `obd`, `dtc` o `event` |

Campos por tipo:

| Tipo | Campos |
| --- | --- |
| `gps` | `lat` [-90, 90], `lon` [-180, 180], `acc_m` ≥ 0 obligatorios; `speed_mps` ≥ 0, `bearing` [0, 360), `alt_m` opcionales |
| `obd` | `values`: objeto no vacío, claves `^[a-z0-9_]{1,32}$`, valores numéricos. Claves conocidas: `rpm`, `speed_kmh`, `coolant_c`, `intake_kpa`, `load_pct`, `throttle_pct`, `voltage_v`, `fuel_rate_lph`. Las desconocidas se aceptan y se guardan (compatibilidad hacia delante) |
| `dtc` | `active` y `pending`: listas de códigos `^[PCBU][0-9A-F]{4}$` (pueden estar vacías) |
| `event` | `event` ∈ {`session_start`, `resumed`, `obd_connected`, `obd_lost`, `obd_error`}; `detail` opcional, ≤ 200 caracteres |

`device_id` sigue `^[a-z0-9-]{1,64}$`; `app_version` es texto de ≤ 32 caracteres.

## 4.3 Respuestas y qué hace la app

| Respuesta | Significado | La app |
| --- | --- | --- |
| `200` `{"accepted": n, "duplicates": n, "rejected": [{"index": i, "id": "…", "error": "…"}]}` | Lote procesado; cada registro se valida por separado | Borra el lote entero de la cola |
| `400` | El lote en sí es inválido (JSON roto, faltan `device_id` o `records`, más de 500 registros) | Lo descarta y lo anota en el registro de errores: nunca tendrá éxito |
| `401` | Token ausente o incorrecto | Conserva el lote y muestra el error en la pantalla de estado y en la notificación |
| `413` | Más de 256 KB | Parte el lote por la mitad y reintenta |
| `5xx` o sin red | Fallo temporal | Reintenta con espera creciente (30 s → 10 min) |

Un duplicado (mismo `id` ya guardado) cuenta en `duplicates` y no modifica lo guardado.

## Versionado

Cualquier cambio incompatible crea `/api/v2/ingest`; `/api/v1/ingest` se mantiene tal cual. Los cambios compatibles (p. ej. nuevas claves `obd` desconocidas) no requieren versión nueva.
