# 03 · Arquitectura y decisiones

## Cómo encajan las piezas

```
┌────────── Coche ──────────┐               ┌──────────── Homelab ────────────┐
│ ELM327 ──Bluetooth──► App │──HTTPS+token─►│ Recepción de datos ──► Base de  │
│               (GPS, cola) │   (Funnel)    │                         datos   │
└───────────────────────────┘               │ API + panel web ◄───────┘  │    │
                                            │ Bot de Telegram ◄──────────┘    │
                                            └─────────────────────────────────┘
Tu navegador ──Tailscale──► panel web
Tu móvil ◄──► Telegram ◄── bot (conexión saliente desde casa)
```

La tablet solo envía datos hacia fuera. Lo único accesible desde internet es el punto de recepción de datos, protegido con un token. El panel solo se ve desde dispositivos de la red Tailscale, y el bot es él quien se conecta a Telegram, de modo que no abre puertos en casa.

## Decisiones y alternativas descartadas

### Fuente de datos del coche

| Opción | Valoración |
| --- | --- |
| **ELM327 por OBD2 (elegida)** | Ya probado con Car Scanner y sin tocar cables. Limitado a OBD2 genérico y lento por la línea K |
| Bus CAN de confort con ESP32 o USB-CAN | Daría datos del ordenador de a bordo, pero requiere electrónica e ingeniería inversa. Queda como mejora futura |
| Datos de la caja CANBUS de la Junsun | Descartada: Junsun no los expone a otras apps |

### Tecnología de la app de la tablet

| Opción | Valoración |
| --- | --- |
| **App nativa en Kotlin (elegida)** | Lo crítico (Bluetooth clásico, arranque al encender, trabajo en segundo plano) es nativo de Android. La app es pequeña y casi sin interfaz |
| Web / PWA | Descartada: Web Bluetooth solo habla BLE (el ELM es clásico), una web no arranca sola y Android la suspende en segundo plano |
| Híbrida con Capacitor | Descartada: obligaría a escribir igualmente en Kotlin el arranque automático, el servicio en segundo plano y la reconexión, con dos tecnologías en vez de una |
| Python en la tablet (el proyecto anterior) | Descartada: python-obd usa un puerto serie que en Android no existe sin root |

### Qué hacer con el proyecto anterior

El proyecto `ocdb-dashboard-app` (FastAPI + python-obd + React, pensado para PC) no encaja en la tablet, pero gran parte se aprovecha. El **backend FastAPI** pasa a ser el servidor de casa (su hoja de ruta ya preveía una fase de sincronización con un servidor). El **frontend React** al final no se reutilizó: el panel es una web estática sin paso de compilación. La **lógica** (lista de PIDs, lectura de averías, modo simulado para desarrollar sin coche) se lleva a la app Kotlin. Hay que revisar el cálculo de consumo: si su último recurso es estimar con el caudal de aire (MAF), en un diésel da valores muy erróneos.

### Cómo llega la tablet al servidor

| Opción | Valoración |
| --- | --- |
| **Tailscale Funnel solo para la recepción de datos (elegida)** | La tablet hace HTTPS normal, sin VPN. Funnel enruta el tráfico de internet a un servicio local a través de los servidores de Tailscale, con certificado automático y sin abrir puertos ni tener IP pública. El cifrado se termina en el homelab |
| Tailscale instalado en la tablet | Válida y más privada, pero añade otra app que debe arrancar sola y mantenerse viva en la Junsun |

Funnel hace el servicio **accesible para cualquiera que conozca la URL**, por eso solo se expone la recepción de datos, protegida con token, y nunca el panel. Si algún día se quisiera el panel sin VPN, habría que añadirle un login robusto.

### Cómo consultar desde el móvil

| Opción | Valoración |
| --- | --- |
| **Bot de Telegram (elegida)** | El bot pregunta a Telegram por mensajes nuevos (long polling), así que solo hace conexiones salientes. Permite consultas (`/donde`, `/estado`, último trayecto, averías) y alertas automáticas |
| App móvil propia | Descartada: un proyecto entero para algo que el bot cubre |
| Vista móvil del panel | Posible, pero requiere estar conectado a Tailscale |

El bot debe responder solo al chat del propietario. Hay que tener en cuenta que los chats con bots no tienen cifrado de extremo a extremo: Telegram puede ver las ubicaciones que envía.

### Cómo saber dónde está aparcado

| Opción | Valoración |
| --- | --- |
| **Lo decide el servidor (elegida)** | Si deja de recibir datos durante unos minutos, el coche está aparcado en el último punto GPS válido recibido |
| Lo decide la tablet al llegar a 0 km/h | Descartada: la tablet puede apagarse sin llegar a enviar nada |

## Qué hace cada parte (sin detalle de implementación)

**App de la tablet.** Arranca sola al encender el coche y trabaja en segundo plano sin interferir con la tablet. Lee el GPS y el ELM327, guarda todo en una cola local para no perder nada sin cobertura y lo envía por lotes al servidor. Tiene una pantalla de estado y ajustes (servidor, token, adaptador) y un modo simulado para desarrollar sin el coche.

**Servidor.** Recibe y guarda los datos; tolera reenvíos sin duplicar. Calcula los trayectos, el estado (en marcha o aparcado y dónde), las alertas (avería nueva, voltaje bajo, temperatura alta, adaptador que no conecta, mantenimiento pendiente) y el kilometraje para el mantenimiento.

**Panel web.** Mapa con la posición o el aparcamiento, lista de trayectos con ruta y gráficas, averías y alertas, y mantenimiento.

El panel ya está implementado dentro del contenedor `api`: una API JSON de solo lectura (`/api/panel/*`) y una web estática sin paso de compilación (módulos ES, con Leaflet y uPlot incluidos en el repositorio). Las teselas de OpenStreetMap pasan por el servidor (`/tiles`, con caché compartida con el bot), así que el navegador nunca habla con OSM. Los trayectos se calculan al vuelo, con una caché en memoria por sesión, y las lecturas del panel usan una conexión SQLite por hilo.

**Bot.** Consultas rápidas desde el móvil y envío de alertas.
