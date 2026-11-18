# Instalación en la tablet (Junsun)

## Comprobaciones

- **El nº de arranque debe aumentar entre ciclos de contacto.** La app identifica cada arranque con
  `Settings.Global.BOOT_COUNT`. Se comprueba en la pantalla Estado: la fila "Arranque nº" debe
  aumentar tras apagar y encender el contacto de nuevo.
  - Si se queda en 0 ("desconocido (0)"), la app recurre a desfases horarios en memoria
    (aceptable).
  - Si se queda en el mismo número mayor que 0, las marcas de tiempo de arranques distintos pueden
    mezclarse: detén la prueba y avisa al desarrollador.
  - Alternativa con adb: `adb logcat -s CarTrace` (línea `BOOT_COUNT=<n>` al iniciar el servicio) o
    `adb shell settings get global boot_count` tras apagar y encender el contacto.
