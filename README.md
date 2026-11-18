# Telemetría 307

Proyecto personal para saber en todo momento dónde está mi Peugeot 307, guardar el histórico de trayectos y detectar a tiempo problemas mecánicos, usando la tablet Android que ya lleva el coche y un servidor propio en casa.

Esta carpeta recoge **la idea, lo que se ha investigado y la solución a la que se ha llegado**. No describe cómo implementarlo: sirve para dar contexto a cualquier persona o agente que vaya a trabajar en el proyecto y para que las decisiones no se vuelvan a discutir desde cero.

## La idea en un párrafo

El coche tiene una tablet Junsun con Android y una SIM con datos. Una app instalada en ella arrancará sola al encender el coche, leerá la ubicación GPS y los datos del motor a través de un adaptador OBD2 ELM327 Bluetooth, y lo enviará todo a un servidor en el homelab. Desde casa se consulta un panel web con mapa, trayectos y estado del coche; desde el móvil, un bot de Telegram responde dónde está aparcado el coche y avisa de averías o de batería baja.

## Solución elegida, de un vistazo

| Pieza | Qué es | Por qué |
| --- | --- | --- |
| App de la tablet | App Android nativa (Kotlin) que arranca sola y trabaja en segundo plano | Una web no puede usar Bluetooth clásico ni arrancar sola |
| Datos del motor | ELM327 Mini Bluetooth en el puerto OBD2 | Ya probado: Car Scanner lee todos los valores en este coche |
| Servidor | Homelab con FastAPI y base de datos, reutilizando el proyecto anterior | Hardware propio, sin servicios de pago |
| Acceso de la tablet al servidor | Tailscale Funnel, solo para el punto de entrada de datos, con token | La tablet no necesita VPN; nada más queda expuesto |
| Panel web | React, accesible solo por Tailscale | Contiene ubicaciones y rutas: no debe ser público |
| Consultas desde el móvil | Bot de Telegram | Sin VPN ni puertos abiertos; además da alertas push. Sustituye a una app móvil |

## Documentos

| Documento | Contenido |
| --- | --- |
| [01 · Visión y alcance](docs/01-vision-y-alcance.md) | Objetivos, qué queda fuera, qué sería un fracaso y qué datos interesan |
| [02 · Hardware y vehículo](docs/02-hardware-y-vehiculo.md) | Peugeot 307, tablet Junsun, ELM327, buses del coche y lo que se ha comprobado |
| [03 · Arquitectura y decisiones](docs/03-arquitectura-y-decisiones.md) | Cómo encajan las piezas y por qué se eligió cada opción frente a las alternativas |
| [04 · Limitaciones y posibles soluciones](docs/04-limitaciones-y-soluciones.md) | Problemas conocidos o previsibles y cómo podrían abordarse |
| [05 · Hoja de ruta y preguntas abiertas](docs/05-hoja-de-ruta-y-preguntas.md) | Fases propuestas y lo que queda por decidir |

## Estado

Fase de diseño cerrada. No hay nada implementado del nuevo enfoque. Existe un proyecto anterior (`ocdb-dashboard-app`: backend FastAPI con python-obd y frontend React) que nunca llegó a conectar con el ELM327 y que se reutilizará en parte para el servidor y el panel.
