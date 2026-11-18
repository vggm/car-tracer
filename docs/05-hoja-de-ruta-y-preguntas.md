# 05 · Hoja de ruta y preguntas abiertas

## Fases propuestas

El orden empieza por lo más incierto, que la app lea el ELM327 de forma estable en la Junsun, y cada fase se valida en el coche antes de pasar a la siguiente.

| Fase | Qué se consigue | Cómo se sabe que funciona |
| --- | --- | --- |
| 1. App mínima | La app arranca sola y lee RPM y velocidad del ELM327 | 30 minutos conduciendo sin cortes |
| 2. GPS y cola local | Posición registrada y guardada aunque no haya cobertura | Un trayecto completo queda guardado en la tablet |
| 3. Recepción en el servidor | Los datos llegan al homelab por Funnel | Un trayecto completo aparece en el servidor, incluso con cortes de cobertura |
| 4. Bot de Telegram | `/donde` y `/estado`; detección de aparcamiento | Primer uso real en el día a día |
| 5. Panel web | Mapa, trayectos y gráficas | Consultar un trayecto desde el navegador |
| 6. Alertas y mantenimiento | Avisos de averías, voltaje, temperatura y mantenimiento | Recibir una alerta real o simulada en Telegram |
| 7. Opcional | Lectura del bus CAN de confort | Datos del ordenador de a bordo en el panel |

La app de la tablet, el servidor y el panel pueden avanzar en paralelo si antes se fija el formato de los datos que se intercambian.

## Pruebas reales que conviene hacer en el coche

Conducir media hora y comprobar que la lectura no se corta y que las RPM coinciden con el cuentarrevoluciones. Quitar el contacto, esperar unos minutos y arrancar sin tocar la tablet, para ver que la app se pone en marcha sola. Entrar y salir de un parking subterráneo y comprobar que los datos llegan al salir. Aparcar y preguntar `/donde` pasados unos minutos. Comparar las averías que muestra el sistema con las que lee Car Scanner. Y una semana de uso normal para confirmar que la navegación, la música y las llamadas no se ven afectadas.

## Preguntas abiertas

| Pregunta | Estado |
| --- | --- |
| Kilómetros actuales del coche, para el mantenimiento | Pendiente; se puede introducir más adelante |
| Versión exacta de Android de la tablet (13 o 14) | No bloquea: una app pensada para Android 14 funciona en ambas |
| ¿Hay datos que quieras añadir o quitar de la propuesta inicial? | La propuesta de [01 · Visión y alcance](01-vision-y-alcance.md) no llegó a confirmarse |
| ¿Se acepta que Telegram vea las ubicaciones que envía el bot? | Asumido; revisable si la privacidad pasa a ser prioritaria |
| ¿Merece la pena el bus CAN de confort? | Para más adelante, según lo útil que resulte el OBD2 |

## Supuestos

El homelab está siempre encendido; si no lo está, la tablet acumula datos y los envía después. La tablet mantiene la SIM con datos. El ELM327 se queda conectado de forma permanente en el puerto OBD2.
