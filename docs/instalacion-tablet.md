# Instalación en la tablet (Junsun) y prueba en modo simulado

Guía para instalar Telemetría 307 en la radio del coche y validar el paso 2 de la hoja de ruta: la app arranca sola, envía datos simulados y `/donde` los refleja. No hace falta el ELM327 ni conducir.

## 0. Lo que necesitas

- El APK firmado: `telemetria-307-0.1.0.apk` (en `dist/` del repo y en la carpeta Descargas de Windows).
- Un pendrive.
- El token de recepción, que está en `~/server-apps/.env` de lnk-server. No lo copies a mano: en el paso 1 se lleva en un fichero.
- La URL del servidor: `https://<servidor>.<tailnet>.ts.net/api/v1/ingest` (la ruta completa, con `/api/v1/ingest`; la tuya la muestra `tailscale funnel status` en el servidor).

## 1. Preparar el pendrive

1. Copia el APK al pendrive.
2. Guarda el token en un fichero de texto del pendrive. Desde WSL, cambiando `<UNIDAD>` por la letra del pendrive en Windows (por ejemplo `e`):

   ```bash
   ssh lnk@<TAILSCALE_IP> "grep '^CAR_TRACE_INGEST_TOKEN=' ~/server-apps/.env | cut -d= -f2- | tr -d '\"'" > /mnt/<UNIDAD>/token.txt
   ```

3. Al terminar la instalación, **borra `token.txt` del pendrive y de la tablet**.

## 2. Instalar el APK

1. Conecta el pendrive a la Junsun y ábrelo con el gestor de archivos.
2. Pulsa el APK. Si Android lo pide, permite instalar apps de origen desconocido para el gestor de archivos.
3. Instala y abre **Telemetría 307**.

## 3. Primera vez: permisos

La app te guía paso a paso. Concede en este orden:

| Paso | Qué elegir |
| --- | --- |
| Ubicación | "Mientras se usa la app" |
| Ubicación en segundo plano | Android abre los ajustes: elige **"Permitir todo el tiempo"** |
| Bluetooth (dispositivos cercanos) | Permitir |
| Notificaciones | Permitir (se puede omitir, pero sirve para ver el estado) |
| Batería | Permitir que la app no se optimice. Si la Junsun no ofrece la pantalla, pulsa "Omitir" |
| Inicio automático | Busca en los ajustes de la Junsun una lista de **inicio automático**, **apps en segundo plano** o similar y añade Telemetría 307. Después pulsa "Hecho" |

Si deniegas un permiso por error y ya no vuelve a aparecer, la app ofrece **"Abrir ajustes de la app"** para concederlo a mano. El botón **"Ajustes"** está disponible en todo momento.

## 4. Ajustes

1. Abre **Ajustes** en la app.
2. **URL del servidor:** la del paso 0.
3. **Token:** abre `token.txt` desde el pendrive, cópialo y pégalo (el ojo muestra u oculta el texto para comprobarlo).
4. Activa el **modo simulado**. El adaptador no hace falta en esta prueba.
5. **Guardar.** Borra `token.txt` del pendrive y de la tablet.

## 5. Pruebas (paso 2 de la hoja de ruta)

Antes de empezar, abre en Telegram el bot del coche y mándale `/start` una vez.

| # | Prueba | Se da por buena si… |
| --- | --- | --- |
| 1 | Con el contacto puesto, abre **Estado** | Servicio activo; "Último envío" pasa a **"Enviado · N/0/0"** en menos de un minuto; los pendientes bajan |
| 2 | Manda `/donde` al bot | Responde **"🚗 En marcha · …"** y una chincheta en el centro de Madrid (es la ruta simulada) |
| 3 | Apunta el **"Arranque nº"** de Estado. Quita el contacto, espera 2 minutos y vuelve a ponerlo **sin tocar la tablet** | Aparece la notificación "Telemetría 307 activa"; en Estado el servicio está activo y **"Arranque nº" ha aumentado**; `/donde` vuelve a decir "En marcha" en un par de minutos |
| 4 | Con el contacto quitado más de 5 minutos, manda `/donde` | Responde **"🅿️ Aparcado desde las HH:MM"** con la última posición |
| 5 | Si la tablet suspende en vez de apagarse (vuelve al instante con lo que tenías abierto), deja el contacto quitado más de 1 minuto y vuelve | Los datos siguen llegando (lo compruebo en el servidor: debe aparecer una sesión nueva con el evento `resumed`) |
| 6 | Usa la navegación, la música y una llamada como siempre | Nada va más lento ni se corta |

### Qué apuntar y mandarme

- El "Arranque nº" antes y después de la prueba 3.
- Lo que ponga en "Último envío" y en "Errores" de la pantalla Estado si algo falla (una foto vale).
- Si la app **no arranca sola** en la prueba 3, dime qué mensaje o notificación ves y lo investigamos con `adb logcat` (paso 4 del plan B10).

### Sobre el "Arranque nº"

La app identifica cada arranque con `Settings.Global.BOOT_COUNT`:

- Si **aumenta** con cada ciclo de contacto: correcto.
- Si se queda en **0** ("desconocido (0)", en rojo): la app usa la hora solo en memoria; es aceptable, pero avísame.
- Si se queda en el **mismo número mayor que 0**: las horas de arranques distintos podrían mezclarse. **Detén la prueba y avísame.**
- Alternativa con adb: `adb logcat -s CarTrace` (línea `BOOT_COUNT=<n>` al iniciar el servicio) o `adb shell settings get global boot_count`.

## 6. Si algo falla

| Síntoma en Estado | Causa probable | Qué hacer |
| --- | --- | --- |
| "Token incorrecto" | Token mal pegado | Vuelve a pegarlo desde el fichero |
| "Reintentando: io: …" | Sin conexión de datos o servidor caído | Comprueba los datos móviles; se reenvía solo al volver la conexión |
| "Reintentando: http 404" | URL sin `/api/v1/ingest` | Corrige la URL |
| El servicio no arranca al poner el contacto | Firmware que cierra apps o falta el autoarranque | Revisa batería e inicio automático (paso 3) |
| "Arranque nº" no cambia | Ver el apartado anterior | Avísame |

## 7. Después de la prueba

No desactives todavía el modo simulado. Cuando vayamos al coche (paso 3, B11), borraré en el servidor los datos simulados, elegirás el ELM327 en Ajustes y desactivarás el modo simulado.
