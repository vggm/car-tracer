# Desarrollo de la app Android

Proyecto Gradle en `android/` (Kotlin, Compose, minSdk 33, targetSdk 34, compileSdk 37).
Las versiones de dependencias viven solo en `android/gradle/libs.versions.toml`.

## Instalar el entorno (WSL, sin sudo)

1. JDK 17 (Eclipse Temurin) desde tarball en `~/.local/share/jdk-17`:
   ```bash
   curl -L -o jdk.tgz "https://api.adoptium.net/v3/binary/latest/17/ga/linux/x64/jdk/hotspot/normal/eclipse"
   mkdir x && tar xzf jdk.tgz -C x && mv x/jdk-* ~/.local/share/jdk-17
   ```
2. Herramientas de línea de comandos del SDK en `~/Android/Sdk/cmdline-tools/latest`
   (zip `commandlinetools-linux-*_latest.zip` de https://developer.android.com/studio, sección "Command line tools only").
3. Variables en `~/.bashrc`:
   ```bash
   export JAVA_HOME="$HOME/.local/share/jdk-17"
   export ANDROID_HOME="$HOME/Android/Sdk"
   export PATH="$JAVA_HOME/bin:$ANDROID_HOME/cmdline-tools/latest/bin:$ANDROID_HOME/platform-tools:$PATH"
   ```
4. Paquetes y licencias:
   ```bash
   yes | sdkmanager --licenses
   sdkmanager "platform-tools" "platforms;android-34" "platforms;android-37.0" "build-tools;34.0.0"
   ```
   (`android-37.0` hace falta como compileSdk porque Compose/OkHttp actuales lo exigen; targetSdk sigue siendo 34.)
5. `android/local.properties` con `sdk.dir=/home/<usuario>/Android/Sdk` (no se versiona).

## Compilar y probar

```bash
cd android
./gradlew test assembleDebug     # tests unitarios + APK debug
./gradlew assembleRelease        # APK release firmado (si existe el keystore)
```

Salidas: `android/app/build/outputs/apk/debug/app-debug.apk` y `.../release/app-release.apk`.

## Firma de release

El keystore está en `~/.android-keys/car-trace.jks` y sus datos en
`~/.android-keys/car-trace.properties` (`storeFile`, `storePassword`, `keyAlias`, `keyPassword`).
Ambos fuera del repo, con permisos 600. Si el fichero de propiedades no existe,
el build funciona y el APK release queda sin firmar. Haz copia de seguridad del keystore:
sin él no se podrán publicar actualizaciones firmadas con la misma clave.

## Instalar el APK en la tablet

- **USB / memoria**: copia `app-release.apk` a la tablet, ábrelo desde el gestor de archivos y permite
  "instalar apps desconocidas" para esa app.
- **adb por Wi-Fi**: en la tablet activa Opciones de desarrollador > Depuración inalámbrica y empareja:
  ```bash
  adb pair <ip>:<puerto-emparejamiento>
  adb connect <ip>:<puerto>
  adb install -r android/app/build/outputs/apk/release/app-release.apk
  ```
