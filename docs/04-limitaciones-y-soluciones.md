# 04 · Limitaciones y posibles soluciones

Problemas conocidos o previsibles, por qué importan y cómo podrían abordarse. Las soluciones son orientativas: indican el camino, no cómo implementarlo.

## Coche y adaptador

| Limitación | Por qué importa | Posibles soluciones |
| --- | --- | --- |
| La centralita va por línea K, un protocolo lento | Pocas lecturas por segundo | Leer en bucle solo 5–6 valores; averías solo al arrancar; voltaje cada minuto |
| El ELM327 es un clon barato | Algunos fallan con la línea K o se desconectan a los pocos segundos | Ya probado con Car Scanner sin problemas. Si fallara, probar un adaptador de calidad (Vgate, OBDLink) antes de buscar el error en la app |
| El OBD2 genérico no da nivel de combustible ni cuentakilómetros | Faltan datos que serían útiles | Kilometraje: valor inicial a mano + suma de la distancia GPS. Más datos: bus CAN de confort en el futuro |
| Consumo en diésel | La estimación por caudal de aire (MAF) no sirve en diésel | Usar el caudal de combustible solo si la centralita lo ofrece; si no, no mostrar consumo |
| El ELM327 tiene corriente con el coche apagado | Puede descargar algo la batería | Comprobar si el modelo se duerme solo; si no, desenchufarlo en paradas largas |
| La caja CANBUS de la Junsun no comparte sus datos | No se pueden aprovechar | Leer el bus CAN de confort directamente (USB-CAN o ESP32 en modo solo escucha), como fase opcional |

## Tablet Junsun

| Limitación | Por qué importa | Posibles soluciones |
| --- | --- | --- |
| Se apaga con el contacto | No hay datos con el coche apagado | Aceptado. El último punto recibido marca el aparcamiento. Alimentación permanente solo si algún día se quiere seguimiento con el coche apagado |
| El firmware cierra apps en segundo plano | La app dejaría de recoger datos | Servicio en primer plano con notificación fija, excluir la app de la optimización de batería y añadirla a la lista de autoarranque del firmware |
| Debe arrancar sin intervención | Si hay que abrirla a mano, el proyecto fracasa | Arrancar la app al encender el sistema; Android 13/14 exige conceder la ubicación en modo "Permitir siempre" |
| Puede suspenderse en vez de apagarse (detectado al planificar) | Al volver, la app sigue abierta pero la conexión Bluetooth está muerta y el trayecto se mezclaría con el anterior | Detectar la vuelta de suspensión, empezar una sesión nueva y reconectar el adaptador |
| Puede arrancar con la hora del sistema incorrecta (detectado al planificar) | Datos con fechas absurdas (año 2000) | Guardar un reloj interno con cada dato y fijar la hora real cuando haya GPS o red, antes de enviar |
| Puede no tener Google Play Services | Algunas librerías de ubicación dependen de ellos | Usar directamente el GPS de Android |
| La ECU puede no responder (contacto puesto sin arrancar, o tablet encendida antes que el motor) | La lectura OBD fallaría al principio | Seguir con el GPS y reintentar el OBD cada vez más espaciado |

## Red y servidor

| Limitación | Por qué importa | Posibles soluciones |
| --- | --- | --- |
| Cobertura irregular: túneles, parkings subterráneos | Se perderían datos | Cola local en la tablet que se vacía al volver la conexión, aunque sea en el siguiente arranque |
| Sin GPS en parkings subterráneos | La posición de aparcamiento sería imprecisa | Conservar y enviar el último punto válido antes de perder la señal |
| El homelab puede estar caído o sin internet | La tablet no podría enviar | La misma cola local; se envía después por partes, primero lo más antiguo |
| La recepción de datos es pública (Funnel) | Cualquiera con la URL puede intentar enviar datos | Token obligatorio, exponer solo ese servicio, limitar el tamaño de los envíos y validar cada dato |
| Un dato mal formado podría bloquear la cola (detectado al planificar) | La tablet reintentaría para siempre | Que el servidor acepte los datos válidos y rechace solo los malos, y que la tablet descarte los rechazados |
| Reenvíos tras cortes | Duplicados en trayectos y alertas | Identificar cada dato de forma única para que reenviar no duplique nada |
| Datos atrasados que llegan días después | Alertas antiguas llegarían como si fueran nuevas | Guardar esas alertas pero no enviarlas a Telegram si el dato es antiguo |
| Telegram no cifra de extremo a extremo los chats con bots | Telegram puede ver las ubicaciones | Aceptado conscientemente. Para máxima privacidad, consultar solo el panel por Tailscale |
| El panel con ubicaciones no debe ser público | Riesgo para la privacidad | Panel solo por Tailscale. Si se quisiera sin VPN, añadir un login robusto antes de exponerlo |

## Datos GPS

| Limitación | Por qué importa | Posibles soluciones |
| --- | --- | --- |
| Puntos erróneos: posición 0,0, baja precisión, saltos imposibles | Moverían el aparcamiento o inflarían las distancias | Ignorar puntos sin precisión suficiente, en 0,0 o con saltos de velocidad imposibles |
| Maniobras de aparcamiento | Crearían trayectos de pocos metros | Descartar trayectos muy cortos |
| Paradas en semáforos o atascos | Partirían un trayecto en varios | Cerrar un trayecto solo tras varios minutos parado |
