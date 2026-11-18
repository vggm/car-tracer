# 01 · Visión y alcance

## Qué se quiere conseguir

El punto de partida fue una pregunta sencilla: si la tablet del coche ya tiene Android e internet, ¿puede enviar por sí sola la ubicación y datos del vehículo a un servidor propio? La respuesta es que sí, y a partir de ahí el proyecto se ha concretado en cinco objetivos.

| Objetivo | Para qué sirve en el día a día |
| --- | --- |
| Saber dónde está el coche | Encontrarlo aparcado, o saber si se ha movido |
| Histórico de trayectos | Ver rutas, distancias y duraciones |
| Salud del coche | Enterarse pronto de averías, batería o alternador débiles y temperaturas anómalas |
| Alertas en el móvil | Recibir avisos sin abrir nada |
| Todo en casa | Datos propios, sin servicios de pago ni terceros más allá de lo imprescindible |

## La idea original de "tres proyectos" y en qué se quedó

Inicialmente se plantearon tres piezas: la app de la tablet, un backend con frontend para consultar los datos y una app móvil para saber dónde quedó aparcado el coche. Durante la conversación la tercera se descartó: un bot de Telegram cubre esa necesidad, funciona sin VPN y además permite recibir alertas. Quedan, por tanto, la app de la tablet y el servidor, del que el bot forma parte.

## Qué datos interesan

Los datos se agrupan según para qué sirven, para no recoger cosas que nunca se van a mirar.

| Grupo | Datos | Comentario |
| --- | --- | --- |
| Trayectos y aparcamiento | Posición GPS (latitud, longitud, precisión, velocidad, rumbo), inicio y fin de trayecto | Lo básico; permite mapa, histórico y "dónde está el coche" |
| Salud del coche | Códigos de avería, voltaje de batería, temperatura del refrigerante, presión del turbo | Las averías son lo más útil; el voltaje lo mide el propio adaptador sin depender de la centralita |
| Conducción y consumo | RPM, velocidad, carga del motor, acelerador; caudal de combustible si la centralita lo da | En diésel, estimar el consumo de otra forma no es fiable |
| Mantenimiento | Kilómetros calculados (no hay sensor) | Se introduce el cuentakilómetros una vez y se suma la distancia GPS; sirve para avisos de aceite, ITV, etc. |

La propuesta inicial es empezar con el primer grupo completo más averías, voltaje, temperatura y RPM, y añadir el resto sin cambiar la arquitectura. Como orientación se habló de enviar posición y datos cada pocos segundos, el voltaje cada minuto y las averías al arrancar. Con ese ritmo el consumo de datos móviles ronda los 150 KB por hora de conducción.

## Fuera de alcance (por ahora)

El seguimiento con el coche apagado queda fuera, porque la tablet se apaga o suspende al quitar el contacto. Tampoco se contempla leer el bus CAN de confort del coche, que queda como mejora futura opcional. No habrá app móvil propia, ya que la cubre el bot. Y la app solo leerá: borrar averías desde ella no entra.

## Qué sería un fracaso aunque funcionara

El proyecto fracasaría si la app molestara al uso normal de la tablet (navegación, música, llamadas), si hubiera que abrirla a mano para que recogiera datos, si el panel o las ubicaciones quedaran expuestos a internet, o si se perdieran datos por falta de cobertura.
