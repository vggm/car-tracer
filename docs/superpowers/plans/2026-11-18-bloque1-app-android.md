# Bloque 1 · App Android · Plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** App para la tablet Junsun que arranca sola, lee el GPS y el ELM327 (o fuentes simuladas), guarda los datos en una cola local y los envía al servidor según el contrato v1.

**Architecture:** Un servicio en primer plano coordina fuentes independientes (GPS, OBD, detector de suspensión), cada una en su corrutina supervisada. Todo pasa por una cola Room, y un `Uploader` la vacía por lotes. La lógica difícil (parser del ELM, reloj, reglas de envío) son clases puras con tests JVM. Los envoltorios de Android son finos.

**Tech Stack:** Kotlin, Gradle KTS con version catalog, coroutines, Room, OkHttp, kotlinx.serialization y Jetpack Compose. Tests con JUnit, kotlinx-coroutines-test, MockWebServer y Robolectric (solo para Room).

**Spec:** `docs/superpowers/specs/2026-11-18-cadena-tablet-servidor-design.md`. Las secciones 4 (contrato) y 6 (app) son normativas.

**Plan hermano:** `docs/superpowers/plans/2026-11-18-bloque1-servidor.md`. Su tarea 1 (contrato y `docs/contract/examples/`) debe estar en `develop` antes de la tarea B2.

## Global Constraints

- `minSdk 33`, `targetSdk 34`, `compileSdk 34` o superior; paquete `dev.lnk.cartrace`; sin Google Play Services.
- Registros y lotes según el contrato v1: lote ≤ 500 registros y ≤ 256 KB.
- Ritmos: GPS cada 3 s; registro `obd` cada 3 s; `ATRV` cada 60 s; averías al empezar la sesión; `Uploader` cada 30 s.
- Esperas: OBD de 5 s a 2 min; envío de 30 s a 10 min.
- Cola con tope de 200.000 filas: si se supera, se borran las más antiguas.
- Suspensión: si `(Δ elapsedRealtime − Δ uptimeMillis)` supera 60 s entre dos ticks (cada 5 s), la tablet ha dormido.
- Servicio en primer plano de tipos `location|connectedDevice`.
- Nunca guardar el token en el repo; el keystore de firma va fuera del repo (`~/.android-keys/`).
- Los commits siguen github-standard: ramas `feat/…` desde `develop`, títulos en inglés.
- Comando de verificación: `cd android && ./gradlew test`. Si toca código de Android: `./gradlew test assembleDebug`.

## Review Focus

1. **Respuestas del ELM327 con ruido**: `SEARCHING...`, `BUS INIT: ...OK`, eco del comando, varias líneas de ECU, `?`, `UNABLE TO CONNECT`, `NO DATA` y el prompt `>`. El parser devuelve `null` o lista vacía y nunca lanza una excepción (tests en B3).
2. **El servidor responde `200` con un cuerpo que no es JSON, o `408`/`429`.** `200` cuenta como procesado; `408` y `429` se tratan como fallo temporal (tests en B6).
3. **Un registro creado antes de un reinicio que nunca tuvo hora fiable**: se descarta y se cuenta, y no bloquea el envío de los posteriores (test en B5).
4. **El adaptador configurado no está emparejado o el Bluetooth está apagado.** La fuente OBD queda en estado "error", reintenta y el GPS sigue (test en B7).
5. **Cambio de los ajustes (URL o token) mientras el servicio corre.** El siguiente envío usa los valores nuevos sin reiniciar (test en B6).

---

### Task B1: Entorno de compilación y esqueleto del proyecto

**Files:**
- Create: `android/settings.gradle.kts`, `android/build.gradle.kts`, `android/gradle/libs.versions.toml`, `android/gradle.properties`, `android/gradlew*` + `android/gradle/wrapper/*`, `android/app/build.gradle.kts`, `android/app/src/main/AndroidManifest.xml`, `android/app/src/main/java/dev/lnk/cartrace/MainActivity.kt` (pantalla vacía)
- Test: `android/app/src/test/java/dev/lnk/cartrace/SmokeTest.kt`
- Create: `docs/desarrollo-android.md` (cómo instalar el entorno y compilar)

- [ ] **Step 1:** Instalar en WSL el JDK 17 (paquete del sistema) y las herramientas de línea de comandos del SDK de Android en `~/Android/Sdk`. Después: `sdkmanager "platform-tools" "platforms;android-34" "build-tools;34.0.0"` y aceptar las licencias. Exportar `ANDROID_HOME` en `~/.bashrc`.
- [ ] **Step 2:** Consultar con Context7 las versiones estables actuales de AGP, Kotlin, el BOM de Compose, Room, OkHttp, kotlinx.serialization, coroutines y Robolectric (KSP para Room), y fijarlas en `libs.versions.toml`. Crear el wrapper de Gradle con la versión que exija AGP.
- [ ] **Step 3:** `SmokeTest` con `assertEquals(4, 2 + 2)`. Ejecutar `./gradlew test assembleDebug`. Esperado: BUILD SUCCESSFUL y `app/build/outputs/apk/debug/app-debug.apk`.
- [ ] **Step 4:** Configurar la firma de release leyendo `~/.android-keys/car-trace.properties`, si existe. Generar el keystore con `keytool` en esa ruta; nunca dentro del repo.
- [ ] **Step 5:** Commit en `feat/android-skeleton`: `chore: 🔧 add android project skeleton`. Integrar en `develop`.

### Task B2: Modelo del contrato en Kotlin

**Files:**
- Create: `android/app/src/main/java/dev/lnk/cartrace/contract/Records.kt`
- Test: `android/app/src/test/java/dev/lnk/cartrace/contract/RecordsTest.kt`

**Interfaces:**
- Produces:
  - `@Serializable sealed interface Record` con `id: String`, `session_id: String`, `seq: Long`, `ts: Long`. Subtipos con `@SerialName`: `GpsRecord(lat, lon, acc_m, speed_mps?, bearing?, alt_m?)`, `ObdRecord(values: Map<String, Double>)`, `DtcRecord(active: List<String>, pending: List<String>)` y `EventRecord(event: String, detail: String?)`.
  - `Batch(device_id, app_version, records: List<Record>)` e `IngestResponse(accepted: Int, duplicates: Int, rejected: List<Rejected>)`.
  - `ContractJson`: la instancia de `Json` con `classDiscriminator = "type"`, `explicitNulls = false` y `encodeDefaults = false`.
  - `Events`: constantes `SESSION_START`, `RESUMED`, `OBD_CONNECTED`, `OBD_LOST` y `OBD_ERROR`.

- [ ] **Step 1: Tests que fallan:**
  - `examplesRoundTrip`: lee `../../docs/contract/examples/valid-mixed.json` (ruta relativa a `android/app`), decodifica `request` como `Batch`, lo vuelve a codificar y compara como `JsonElement`. Los números se comparan como valor: `88` y `88.0` son iguales.
  - `optionalGpsFieldsOmittedWhenNull`;
  - `responseDecodesRejected`.
- [ ] **Step 2:** Ejecutar `./gradlew test --tests '*RecordsTest*'`. Esperado: FAIL.
- [ ] **Step 3:** Implementar `Records.kt`.
- [ ] **Step 4:** Ejecutar. Esperado: PASS.
- [ ] **Step 5:** Commit en `feat/android-core`: `feat: ✨ add contract v1 models`.

### Task B3: `ElmParser`

**Files:**
- Create: `android/app/src/main/java/dev/lnk/cartrace/obd/ElmParser.kt`, `android/app/src/main/java/dev/lnk/cartrace/obd/Pids.kt`
- Test: `android/app/src/test/java/dev/lnk/cartrace/obd/ElmParserTest.kt`

**Interfaces:**
- Produces:
  - `enum class Pid(val cmd: String, val key: String)`: `RPM("010C", "rpm")`, `SPEED("010D", "speed_kmh")`, `COOLANT("0105", "coolant_c")`, `INTAKE("010B", "intake_kpa")`, `LOAD("0104", "load_pct")`, `THROTTLE("0111", "throttle_pct")` y `FUEL_RATE("015E", "fuel_rate_lph")`.
  - `object ElmParser`:
    - `clean(raw: String): List<String>`: quita el eco, `>`, `SEARCHING...`, `BUS INIT: ...`, los espacios y las líneas vacías.
    - `value(pid: Pid, raw: String): Double?`: aplica la fórmula SAE estándar de cada PID: RPM `(256A+B)/4`; velocidad `A`; refrigerante `A−40`; admisión `A`; carga y acelerador `A·100/255`; caudal `(256A+B)/20`.
    - `supportedPids(responses: List<String>): Set<String>`: decodifica las máscaras de `0100`, `0120` y `0140` a comandos `01XX`.
    - `dtcs(raw: String, mode: Char): List<String>`: modo `'3'` responde con `43`, modo `'7'` con `47`; cada par de bytes es un código, los `0000` se descartan; la primera letra según los dos bits altos (`P`/`C`/`B`/`U`).
    - `voltage(raw: String): Double?`, a partir de `"12.6V"`.
    - `isError(raw: String): Boolean`: `NO DATA`, `UNABLE TO CONNECT`, `?`, `STOPPED`, `CAN ERROR`, `BUS ERROR`, `ERROR`.

- [ ] **Step 1: Tests que fallan:**
  - `rpm("41 0C 1A F8")` = 1726.0; `speed("410D32")` = 50.0; `coolant("41 05 7B")` = 83.0;
  - `supportedPids` con `"41 00 BE 3E B8 13"` contiene `010C` y `010D`;
  - `dtcs("43 01 33 00 00 00 00", '3')` = `["P0133"]`; `dtcs("43 41 23 …")` empieza por `C`;
  - `voltage("12.6V")` = 12.6;
  - `noisyResponses` (Review Focus 1), parametrizado: `"SEARCHING...\r41 0C 1A F8\r\r>"` = 1726.0; `"BUS INIT: ...OK\r41 0D 00"` = 0.0; `"NO DATA"`, `"?"`, `"UNABLE TO CONNECT"`, `""` y `"41 0C 1A"` (corta) → `null`, sin excepción;
  - `multiEcuLinesTakesFirstValid`.
- [ ] **Step 2:** Ejecutar. Esperado: FAIL.
- [ ] **Step 3:** Implementar.
- [ ] **Step 4:** Ejecutar. Esperado: PASS.
- [ ] **Step 5:** Commit en `feat/android-core`: `feat: ✨ add elm327 response parser`.

### Task B4: `SessionClock`, `SleepDetector` y sesiones

**Files:**
- Create: `android/app/src/main/java/dev/lnk/cartrace/core/Clocks.kt`, `core/SessionClock.kt`, `core/SleepDetector.kt`, `core/Session.kt`
- Test: `android/app/src/test/java/dev/lnk/cartrace/core/SessionClockTest.kt`, `SleepDetectorTest.kt`

**Interfaces:**
- Produces:
  - `interface Clocks { fun elapsedMs(): Long; fun uptimeMs(): Long; fun wallMs(): Long; fun bootCount(): Int }`, con `AndroidClocks` (que usa `Settings.Global.BOOT_COUNT`) y `FakeClocks` en los tests.
  - `Stamp(bootCount: Int, elapsedMs: Long, wallMs: Long)` y `Clocks.stamp(): Stamp`.
  - `class SessionClock(minWallMs: Long)`:
    - `onGpsFix(bootCount: Int, gpsUtcMs: Long, elapsedMs: Long)` guarda el offset de ese arranque y conserva el primero;
    - `resolve(stamp: Stamp, offsets: Map<Int, Long>, currentBoot: Int): Resolution`, donde `Resolution` es `Ts(Long) | Wait | Drop`. Reglas de la spec 6.3: GPS → `wallMs` si ≥ `minWallMs` → `Wait` si el arranque es el actual → `Drop` si es de un arranque anterior.
    - `minWallMs` = `BuildConfig.BUILD_TIME_MS`.
  - `class SleepDetector(clocks: Clocks, thresholdMs: Long = 60_000)` con `tick(): Boolean` (`true` si ha dormido desde el tick anterior).
  - `class Session(val id: String = UUID…)` con `nextSeq(): Long`, que empieza en 0.

- [ ] **Step 1: Tests que fallan:**
  - `gpsOffsetWins`; `wallUsedWhenPlausible`; `waitsInCurrentBootWithoutTime`; `dropsPreviousBootWithoutTime`; `firstOffsetKept`;
  - `sleepDetectedWhenElapsedJumps` (elapsed +120 s, uptime +5 s) y `noSleepOnNormalTick` (los dos +5 s);
  - `seqIsMonotonic`.
- [ ] **Step 2:** Ejecutar. Esperado: FAIL.
- [ ] **Step 3:** Implementar y añadir el campo `BUILD_TIME_MS` a `BuildConfig` en `app/build.gradle.kts`.
- [ ] **Step 4:** Ejecutar. Esperado: PASS.
- [ ] **Step 5:** Commit: `feat: ✨ add session clock and sleep detector`. Integrar `feat/android-core` (B2–B4) en `develop`.

### Task B5: Cola local (Room)

**Files:**
- Create: `android/app/src/main/java/dev/lnk/cartrace/queue/PendingRecord.kt`, `queue/QueueDao.kt`, `queue/AppDatabase.kt`, `queue/RecordQueue.kt`
- Test: `android/app/src/test/java/dev/lnk/cartrace/queue/RecordQueueTest.kt` (Robolectric, Room en memoria)

**Interfaces:**
- Consumes: `Record` y `ContractJson` (B2); `Stamp`, `SessionClock` y `Resolution` (B4).
- Produces:
  - La entidad `PendingRecord(rowId autogen, id: String, bootCount: Int, elapsedMs: Long, wallMs: Long, json: String)`. El `json` es el registro serializado con `ts = 0`, y el `ts` real se inyecta al enviar.
  - `class RecordQueue(dao, clock: SessionClock, maxRows: Int = 200_000)`:
    - `suspend fun add(record: Record, stamp: Stamp)`: inserta y, si se supera `maxRows`, borra las más antiguas;
    - `suspend fun nextBatch(maxRecords: Int, offsets: Map<Int, Long>, currentBoot: Int): ReadyBatch`: recorre las filas por `rowId` ascendente, resuelve el `ts`, elimina las `Drop` (las cuenta en `droppedCount`) y se detiene en la primera `Wait`;
    - `suspend fun remove(rowIds: List<Long>)`, `suspend fun size(): Int` y `val droppedCount: StateFlow<Int>`.
  - `ReadyBatch(rowIds: List<Long>, records: List<Record>)`, con los registros ya con `ts`.
  - Los offsets de GPS se guardan en la tabla `boot_offsets(bootCount PK, offsetMs)`, con `QueueDao.saveOffset` y `QueueDao.offsets()`.

- [ ] **Step 1: Tests que fallan:**
  - `fifoOrderAndTsInjection`;
  - `capDeletesOldest` (con `maxRows = 10` e insertando 12);
  - `previousBootWithoutTimeIsDroppedAndCounted` (Review Focus 3): las filas posteriores, que sí tienen hora, salen en el mismo lote;
  - `stopsAtFirstWaitInCurrentBoot`.
- [ ] **Step 2:** Ejecutar. Esperado: FAIL.
- [ ] **Step 3:** Implementar con Room (KSP).
- [ ] **Step 4:** Ejecutar. Esperado: PASS.
- [ ] **Step 5:** Commit en `feat/android-upload`: `feat: ✨ add local record queue`.

### Task B6: `Uploader` y ajustes

**Files:**
- Create: `android/app/src/main/java/dev/lnk/cartrace/upload/Uploader.kt`, `upload/UploadPolicy.kt`, `settings/AppSettings.kt`
- Test: `android/app/src/test/java/dev/lnk/cartrace/upload/UploaderTest.kt`, `UploadPolicyTest.kt`

**Interfaces:**
- Consumes: `RecordQueue` y `ReadyBatch` (B5); `Batch`, `IngestResponse` y `ContractJson` (B2).
- Produces:
  - `AppSettings` (sobre `SharedPreferences`) con `serverUrl`, `token`, `adapterAddress`, `simulated` y `deviceId` (por defecto `"junsun-307"`), y `val changes: StateFlow<SettingsSnapshot>`.
  - `sealed interface UploadOutcome`: `Sent(accepted, duplicates, rejected)`, `Discarded(status)` (400), `Unauthorized`, `TooLarge`, `Retry(reason)` y `Idle`.
  - `object UploadPolicy`: `classify(code: Int): UploadOutcomeKind` (200–299 enviado; 400 descartar; 401 sin autorización; 413 demasiado grande; 408, 429 y 5xx reintentar; el resto, descartar) y `nextDelayMs(failures: Int): Long` (30 s × 2^n, con tope en 600 s).
  - `class Uploader(queue, settings, http: OkHttpClient, appVersion: String)` con `suspend fun uploadOnce(maxRecords: Int = 500): UploadOutcome`. Lee los ajustes en cada llamada. Antes de enviar, si el JSON pasa de 262144 bytes, parte el lote por la mitad. Con `413`, reintenta con la mitad hasta llegar a 1 registro, y ese se descarta. Las respuestas `Sent` y `Discarded` borran las filas del lote.

- [ ] **Step 1: Tests que fallan**, con MockWebServer:
  - `sends200RemovesRows`; `discards400`; `keepsRowsOn401`; `retriesOn5xx`;
  - `splitsOn413` (el servidor responde `413` si hay más de 2 registros);
  - `nonJson200CountsAsSent` y `408And429Retry` (Review Focus 2);
  - `usesUpdatedSettingsWithoutRestart` (Review Focus 5);
  - `sendsBearerAndJson`;
  - `backoffSequence`: 30, 60, 120, 240, 480, 600 y 600 s.
- [ ] **Step 2:** Ejecutar. Esperado: FAIL.
- [ ] **Step 3:** Implementar.
- [ ] **Step 4:** Ejecutar. Esperado: PASS.
- [ ] **Step 5:** Commit: `feat: ✨ add uploader with retry policy`. Integrar `feat/android-upload` en `develop`.

### Task B7: Fuentes de datos, reales y simuladas

**Files:**
- Create: `android/app/src/main/java/dev/lnk/cartrace/obd/ElmTransport.kt`, `obd/BluetoothElmTransport.kt`, `obd/ObdSource.kt`, `gps/GpsSource.kt`, `sim/FakeElmTransport.kt`, `sim/FakeGpsSource.kt`, `sim/route.json` (en `src/main/assets/`)
- Test: `android/app/src/test/java/dev/lnk/cartrace/obd/ObdSourceTest.kt`, `sim/FakeGpsSourceTest.kt`

**Interfaces:**
- Consumes: `ElmParser` y `Pid` (B3); `Session`, `Clocks` y `Stamp` (B4); `Record` y `Events` (B2).
- Produces:
  - `interface ElmTransport { suspend fun open(); suspend fun command(cmd: String, timeoutMs: Long = 3000): String; fun close() }`. `BluetoothElmTransport(address)` usa `createRfcommSocketToServiceRecord(UUID 00001101-0000-1000-8000-00805F9B34FB)` y lee hasta el `>`.
  - `class ObdSource(transportFactory: () -> ElmTransport, clocks, emit: suspend (Record, Stamp) -> Unit, sessionProvider: () -> Session)`:
    - `suspend fun run()`: un bucle que no termina hasta que se cancela;
    - `val state: StateFlow<ObdState>`, con los estados `Connecting`, `Connected(protocol)` y `Retrying(error, nextInMs)`.
    - Comportamiento según la spec 6.2: inicialización (`ATZ`, `ATE0`, `ATL0`, `ATS0`, `ATH0`, `ATSP0` y `ATDPN` guardado); PIDs soportados y `DtcRecord` al conectar; bucle de lectura; `ObdRecord` cada 3 s con los últimos valores; `voltage_v` cada 60 s; eventos `obd_connected` y `obd_lost`; espera de 5 s → 2 min.
  - `data class GpsFix(utcMs: Long, lat: Double, lon: Double, accM: Double, speedMps: Double?, bearing: Double?, altM: Double?)`.
  - `interface GpsSource { fun start(onFix: (GpsFix) -> Unit); fun stop() }`, con `AndroidGpsSource` (`LocationManager.GPS_PROVIDER`, 3000 ms, 0 m) y `FakeGpsSource` (recorre `route.json` a 50 km/h).
  - `ObdSource` emite `obd_error` (con `detail`) cuando el ELM responde a la inicialización con un error persistente (`UNABLE TO CONNECT` tras 3 intentos), además de pasar a `Retrying`.
  - `FakeElmTransport`: responde a cada comando con valores verosímiles que varían en el tiempo (RPM entre 800 y 2.500, refrigerante que sube hasta 88 °C) y `NO DATA` en `015E`.

- [ ] **Step 1: Tests que fallan**, con `runTest` y tiempo virtual:
  - `initSequenceAndConnectedEvent`;
  - `emitsDtcOnConnect`;
  - `emitsObdEvery3s` (avanzar 9 s → 3 registros `obd`);
  - `voltageEvery60s`;
  - `skipsUnsupportedPid` (`015E` nunca se pide si no aparece en la máscara);
  - `ioErrorEmitsLostAndBacksOff` (5 s y después 10 s);
  - `transportOpenFailsKeepsRetrying` (Review Focus 4: `open()` lanza `IOException("not paired")` → estado `Retrying` sin excepción);
  - `fakeGpsMovesAlongRoute`.
- [ ] **Step 2:** Ejecutar. Esperado: FAIL.
- [ ] **Step 3:** Implementar.
- [ ] **Step 4:** Ejecutar. Esperado: PASS.
- [ ] **Step 5:** Commit en `feat/android-sources`: `feat: ✨ add obd and gps sources with simulators`. Integrar en `develop`.

### Task B8: `TelemetryService`, `BootReceiver` y manifiesto

**Files:**
- Create: `android/app/src/main/java/dev/lnk/cartrace/service/TelemetryService.kt`, `service/Supervisor.kt`, `service/BootReceiver.kt`, `service/Status.kt`
- Modify: `android/app/src/main/AndroidManifest.xml`
- Test: `android/app/src/test/java/dev/lnk/cartrace/service/SupervisorTest.kt`

**Interfaces:**
- Consumes: todo lo anterior.
- Produces:
  - `class Supervisor(scope)` con `fun launch(name: String, block: suspend () -> Unit)`: si `block` lanza una excepción (que no sea de cancelación), la registra en `Status.errors` y lo relanza tras 5 s.
  - `object Status` (StateFlows que lee la interfaz): `serviceRunning`, `obd: ObdState`, `lastFix: GpsFix?`, `queueSize`, `lastUpload: Pair<Long, UploadOutcome>?`, `dropped` y `errors: List<String>` (los últimos 20).
  - `TelemetryService`:
    - En `onCreate` llama a `startForeground` con los tipos `LOCATION or CONNECTED_DEVICE` y la notificación "Telemetría 307 activa · N pendientes" (o el error `401`).
    - Lanza con el `Supervisor`: GPS (real o simulado según `AppSettings.simulated`), OBD, `Uploader` cada 30 s con espera creciente, y un tick de `SleepDetector` cada 5 s.
    - Al dormir: emite `resumed`, crea un `Session` nuevo y reinicia el OBD.
    - Al crear cada sesión emite `session_start`.
    - Cada fix de GPS llama a `SessionClock.onGpsFix` y a `QueueDao.saveOffset`.
  - `BootReceiver`: con `BOOT_COMPLETED`, `android.intent.action.QUICKBOOT_POWERON` y `MY_PACKAGE_REPLACED` llama a `startForegroundService`, pero solo si los permisos de ubicación en segundo plano y de Bluetooth están concedidos; si no, no hace nada.
  - Manifiesto: `INTERNET`, `ACCESS_FINE_LOCATION`, `ACCESS_BACKGROUND_LOCATION`, `BLUETOOTH_CONNECT`, `FOREGROUND_SERVICE`, `FOREGROUND_SERVICE_LOCATION`, `FOREGROUND_SERVICE_CONNECTED_DEVICE`, `POST_NOTIFICATIONS`, `RECEIVE_BOOT_COMPLETED`, `REQUEST_IGNORE_BATTERY_OPTIMIZATIONS`; el servicio con `foregroundServiceType="location|connectedDevice"`.

- [ ] **Step 1: Tests que fallan:** `supervisorRestartsCrashedChild`, `supervisorDoesNotRestartOnCancel` y `supervisorRecordsError`.
- [ ] **Step 2:** Ejecutar. Esperado: FAIL.
- [ ] **Step 3:** Implementar el `Supervisor`, el servicio, el receptor y el manifiesto.
- [ ] **Step 4:** Ejecutar `./gradlew test assembleDebug`. Esperado: PASS y BUILD SUCCESSFUL.
- [ ] **Step 5:** Commit en `feat/android-service`: `feat: ✨ add telemetry foreground service and boot receiver`.

### Task B9: Pantallas (Estado, Ajustes, Primera vez)

**Files:**
- Create: `android/app/src/main/java/dev/lnk/cartrace/ui/StatusScreen.kt`, `ui/SettingsScreen.kt`, `ui/OnboardingScreen.kt`, `ui/Permissions.kt`
- Modify: `MainActivity.kt`
- Test: `android/app/src/test/java/dev/lnk/cartrace/ui/PermissionsTest.kt`

**Interfaces:**
- Consumes: `Status`, `AppSettings` y `TelemetryService`.
- Produces: `Permissions.nextStep(granted: Set<String>, batteryExempt: Boolean): OnboardingStep?`. Orden: `FINE_LOCATION` → `BACKGROUND_LOCATION` → `BLUETOOTH_CONNECT` → `POST_NOTIFICATIONS` → `BATTERY` → `AUTOSTART_INFO` → `null` (todo listo). Al terminar la primera vez se arranca el servicio desde la actividad visible.

- [ ] **Step 1: Tests que fallan:** `orderIsFineThenBackground`, `skipsGranted` y `doneWhenAllGranted`.
- [ ] **Step 2:** Ejecutar. Esperado: FAIL.
- [ ] **Step 3:** Implementar `Permissions` y las tres pantallas con Compose:
  - Ajustes: la lista de dispositivos emparejados sale de `BluetoothAdapter.bondedDevices`, y la URL se valida (`https://` o `http://`).
  - Primera vez: el paso de autoarranque muestra el texto "Añade Telemetría 307 a la lista de inicio automático de la Junsun (Ajustes → Aplicaciones → Inicio automático o similar)."
- [ ] **Step 4:** Ejecutar `./gradlew test assembleDebug`. Esperado: PASS.
- [ ] **Step 5:** Commit: `feat: ✨ add status, settings and onboarding screens`. Integrar `feat/android-service` (B8 y B9) en `develop`.

### Task B10: APK firmado, guía de instalación y validación del paso 2

Necesita a Víctor y la tablet. Lo coordina la sesión principal.

**Files:**
- Create: `docs/instalacion-tablet.md`: instalar el APK, permisos, autoarranque, URL y token, modo simulado y cómo enviar los logs (`adb logcat -s CarTrace`).

- [ ] **Step 1:** Ejecutar `./gradlew assembleRelease`. Esperado: `app-release.apk` firmado (`apksigner verify` → OK).
- [ ] **Step 2:** Víctor instala el APK, completa la primera vez con el modo simulado activado y escribe la URL de Funnel y el token.
- [ ] **Step 3:** Validación del paso 2 (spec 8.2):
  - **Contacto:** se quita y se pone sin tocar la tablet → la app está en marcha (notificación visible), los datos llegan (`SELECT COUNT(*) FROM records` sube) y `/donde` muestra "En marcha".
  - **Suspensión:** se deja dormir más de 1 minuto y se despierta → aparece un `session_id` nuevo con un evento `resumed`.
  - **Uso normal:** la navegación y la música funcionan con normalidad.
- [ ] **Step 4:** Si el arranque automático falla, investigar con `adb logcat` qué difunde la Junsun al poner el contacto. Añadir esa acción a `BootReceiver` y repetir el paso 3.

### Task B11: Validación del paso 3 en el coche (manual)

- [ ] **Step 1:** Desactivar el modo simulado y elegir el ELM327 en Ajustes.
- [ ] **Step 2:** Pruebas de la spec 8.2, paso 3:
  - 30 minutos conduciendo sin `obd_lost`, con las RPM cuadrando con el cuentarrevoluciones;
  - entrar y salir de un parking subterráneo → los datos llegan al salir;
  - las averías coinciden con las que lee Car Scanner;
  - `/donde` encuentra el coche aparcado.
- [ ] **Step 3:** Anotar las incidencias en Engram y, si hacen falta cambios, abrir el bloque siguiente con su propia spec.
