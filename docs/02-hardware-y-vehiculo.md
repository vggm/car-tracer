# 02 · Hardware y vehículo

## El coche: Peugeot 307 1.6 HDi de 2007

Es un diésel con turbo. Para este proyecto importan dos redes distintas dentro del coche.

**La centralita del motor**, que es la que se lee por el puerto OBD2. En los Peugeot de esa época va por la línea K del conector (pin 7), un protocolo antiguo y lento. Esto limita cuántos valores se pueden leer por segundo: lo razonable es consultar en bucle unos cinco o seis.

**El bus de confort**, por donde circulan datos como el ordenador de a bordo, las puertas o la temperatura exterior. PSA usó el bus VAN hasta 2005 y lo sustituyó por CAN a partir de 2006, así que este coche (2007) usa **CAN**, dentro de la arquitectura que PSA llama AEE2004. Es más fácil de leer que el VAN y hay documentación de la comunidad (por ejemplo, el proyecto PSA-RE), aunque no es oficial y puede contener errores.

## El adaptador: ELM327 Mini Bluetooth

Es el clásico adaptador azul, un clon chino que usa **Bluetooth clásico** (perfil serie, SPP), no Bluetooth de baja energía. Se empareja una vez desde los ajustes de Android con PIN 1234 o 0000.

Se ha comprobado con la app **Car Scanner** instalada en la propia tablet: conecta sin problemas y lee todos los valores que ofrece la app. Esto confirma que el adaptador, la tablet y el coche son compatibles, y que una app propia puede hacer lo mismo.

Dos avisos que salieron en la investigación. Los clones de ELM327 a veces tienen fallos de firmware con los protocolos de línea K, y hay casos documentados de 307 en los que el adaptador se desconectaba a los pocos segundos con otras apps. Por ahora no ha pasado, pero si apareciera, lo primero sería probar un adaptador de mejor calidad. Además, el puerto OBD2 suele tener corriente con el coche apagado, así que el adaptador puede gastar algo de batería; algunos se duermen solos y otros conviene desenchufarlos si el coche va a estar parado mucho tiempo.

## Qué ofrece el OBD2 genérico y qué no

Por OBD2 genérico se obtienen RPM, velocidad, temperatura del motor, carga, presión de admisión (turbo), códigos de avería activos y pendientes y, a veces, el caudal de combustible. El voltaje lo da el propio adaptador. En cambio, el **nivel de combustible y el cuentakilómetros** normalmente **no** están disponibles. Para el mantenimiento, el kilometraje se calculará sumando la distancia GPS a partir de un valor introducido a mano.

## La tablet: Junsun con Android

Es una unidad de radio Android de la marca Junsun, con **Android 13 o 14** y una **SIM con datos móviles**. Tiene Bluetooth utilizable por apps, como demuestra Car Scanner. No hay garantía de que tenga los servicios de Google Play, así que lo prudente es no depender de ellos.

Lleva una **caja CANBUS** (decodificador) que lee el bus de confort del coche para mostrar datos en la radio, pero Junsun **no da acceso a esos datos a apps de terceros**. Existen proyectos de ingeniería inversa del protocolo entre estas radios y la caja CAN en coches PSA, pero usarlos implica electrónica adicional.

Como muchas unidades de este tipo, se apaga o se suspende al quitar el contacto, y su firmware tiende a cerrar apps en segundo plano. Ver [04 · Limitaciones](04-limitaciones-y-soluciones.md).

## El servidor: homelab

Equipo en casa, encendido de forma continua, sin IP pública y con **Tailscale** instalado. Ahí correrán el servidor, la base de datos, el panel y el bot.

## Vía futura opcional: leer el bus CAN de confort

Si algún día se quieren datos del ordenador de a bordo que el OBD2 no da, hay dos caminos posibles, siempre conectándose en paralelo a los cables CAN que ya usa la caja de la Junsun y en modo solo escucha. Uno es un adaptador USB-CAN conectado a la tablet; el otro, un ESP32 con transceptor CAN que envíe los datos a la tablet por Bluetooth. Ambos dependen de qué mensajes estén descifrados en la documentación de la comunidad.
