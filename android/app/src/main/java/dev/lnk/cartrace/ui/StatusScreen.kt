package dev.lnk.cartrace.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import dev.lnk.cartrace.obd.ObdState
import dev.lnk.cartrace.service.Status

@Composable
fun StatusScreen() {
    val running by Status.serviceRunning.collectAsStateWithLifecycle()
    val obd by Status.obd.collectAsStateWithLifecycle()
    val fix by Status.lastFix.collectAsStateWithLifecycle()
    val queue by Status.queueSize.collectAsStateWithLifecycle()
    val upload by Status.lastUpload.collectAsStateWithLifecycle()
    val dropped by Status.dropped.collectAsStateWithLifecycle()
    val errors by Status.errors.collectAsStateWithLifecycle()

    Column(
        Modifier.verticalScroll(rememberScrollState()).padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        Line("Servicio", if (running) "Activo" else "Detenido")
        Line(
            "OBD",
            when (val s = obd) {
                ObdState.Connecting -> "Conectando…"
                is ObdState.Connected -> "Conectado (${s.protocol})"
                is ObdState.Retrying -> "Reintentando: ${s.error} (en ${s.nextInMs / 1000} s)"
            },
        )
        Line(
            "Último GPS",
            fix?.let { "${Formatters.time(it.utcMs)} · precisión ${"%.0f".format(it.accM)} m" } ?: "Sin fix",
        )
        Line("En cola", queue.toString())
        Line(
            "Última subida",
            upload?.let { (at, o) -> "${Formatters.time(at)} · ${Formatters.outcome(o)}" } ?: "Aún ninguna",
        )
        Line("Descartados (cola llena)", dropped.toString())
        Text("Últimos errores", style = MaterialTheme.typography.titleMedium)
        if (errors.isEmpty()) Text("Ninguno") else errors.asReversed().forEach { Text(it, style = MaterialTheme.typography.bodySmall) }
    }
}

@Composable
private fun Line(label: String, value: String) {
    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
        Text(label, style = MaterialTheme.typography.titleMedium)
        Text(value, style = MaterialTheme.typography.bodyLarge)
    }
}
