package dev.lnk.cartrace.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Button
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp

@Composable
fun OnboardingScreen(
    step: OnboardingStep,
    permanentlyDenied: Boolean,
    onAction: () -> Unit,
    onOpenAppSettings: () -> Unit,
    onSkip: (() -> Unit)?,
    onOpenSettings: () -> Unit,
) {
    val (title, body, button) = when (step) {
        OnboardingStep.FINE_LOCATION -> Triple(
            "Ubicación",
            "Telemetría 307 necesita la ubicación precisa para registrar el recorrido.",
            "Conceder ubicación",
        )
        OnboardingStep.BACKGROUND_LOCATION -> Triple(
            "Ubicación en segundo plano",
            "Para seguir registrando con la pantalla apagada, elige «Permitir siempre» en los ajustes que se abrirán.",
            "Abrir ajustes de ubicación",
        )
        OnboardingStep.BLUETOOTH_CONNECT -> Triple(
            "Bluetooth",
            "Necesario para conectar con el adaptador OBD.",
            "Conceder Bluetooth",
        )
        OnboardingStep.POST_NOTIFICATIONS -> Triple(
            "Notificaciones",
            "Permite la notificación persistente que mantiene el servicio activo.",
            "Conceder notificaciones",
        )
        OnboardingStep.BATTERY -> Triple(
            "Batería",
            "Excluye la app de la optimización de batería para que no se detenga.",
            "Excluir de la optimización",
        )
        OnboardingStep.AUTOSTART_INFO -> Triple(
            "Inicio automático",
            "Añade Telemetría 307 a la lista de inicio automático de la Junsun (Ajustes → Aplicaciones → Inicio automático o similar).",
            "Hecho",
        )
    }
    Column(Modifier.padding(24.dp), verticalArrangement = Arrangement.spacedBy(16.dp)) {
        Text("Configuración inicial", style = MaterialTheme.typography.headlineSmall)
        Text(title, style = MaterialTheme.typography.titleLarge)
        Text(body)
        Button(onClick = onAction) { Text(button) }
        if (permanentlyDenied) {
            Text("El permiso fue denegado. Concédelo desde los ajustes de la app.")
            Button(onClick = onOpenAppSettings) { Text("Abrir ajustes de la app") }
        }
        if (onSkip != null) TextButton(onClick = onSkip) { Text("Omitir") }
        TextButton(onClick = onOpenSettings) { Text("Ajustes") }
    }
}
