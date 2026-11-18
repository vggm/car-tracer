# Ejemplos del contrato de ingesta v1

Ficheros compartidos que consumen **tanto los tests del servidor como los de la app Android**. No se duplican: cualquier cambio aquí afecta a ambas suites.

## Formato de los `.json`

```json
{"description": "...", "request": { /* lote completo */ },
 "expected_status": 200,
 "expected": {"accepted": 4, "duplicates": 0, "rejected_indexes": []}}
```

- `description`: qué comprueba el caso.
- `request`: el cuerpo del `POST /api/v1/ingest`, tal cual.
- `expected_status`: código HTTP esperado.
- `expected`: para `200`, `accepted`, `duplicates` y `rejected_indexes` (índices de `records` rechazados, en orden). Para `400` es `null`.

## Fichero crudo

`batch-not-json.txt` es un cuerpo crudo (no JSON válido) que debe dar `400`.

## Casos

| Fichero | Esperado |
| --- | --- |
| `valid-mixed.json` | 200, 6 aceptados |
| `partial-reject.json` | 200, 3 aceptados, 1 duplicado, rechazados `[3, 4, 5]` |
| `batch-missing-device.json` | 400 (falta `device_id`) |
| `batch-not-json.txt` | 400 (JSON roto) |

Los `ts` de los registros válidos están entre 1763481000000 y 1763481600000; los tests usan un reloj fijo de 1763481600000.
