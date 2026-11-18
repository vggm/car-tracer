# Instalación en la tablet (Junsun)

## Comprobaciones

- **BOOT_COUNT debe aumentar entre ciclos de contacto.** La app identifica cada arranque con
  `Settings.Global.BOOT_COUNT` (se registra en logcat, etiqueta `CarTrace`, al iniciar el servicio:
  `BOOT_COUNT=<n>`). Comprobarlo con `adb logcat -s CarTrace` o
  `adb shell settings get global boot_count` tras apagar y encender el contacto. Si no aumenta
  (o vale 0), la app solo guarda el desfase horario en memoria, pero las marcas de tiempo de
  arranques sin hora fiable se pueden perder tras reiniciar el servicio.
