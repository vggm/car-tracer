package dev.lnk.cartrace.ui

import android.Manifest
import android.annotation.SuppressLint
import android.bluetooth.BluetoothManager
import android.content.Context
import android.content.pm.PackageManager
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.selection.selectable
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.RadioButton
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.text.input.VisualTransformation
import androidx.compose.ui.unit.dp
import dev.lnk.cartrace.service.AppGraph

private data class Bonded(val name: String, val address: String)

@SuppressLint("MissingPermission")
private fun bondedDevices(ctx: Context): List<Bonded>? {
    if (ctx.checkSelfPermission(Manifest.permission.BLUETOOTH_CONNECT) != PackageManager.PERMISSION_GRANTED) return null
    val adapter = ctx.getSystemService(BluetoothManager::class.java)?.adapter ?: return emptyList()
    return try {
        adapter.bondedDevices.orEmpty().map { Bonded(it.name ?: it.address, it.address) }
    } catch (e: SecurityException) {
        null
    }
}

@Composable
fun SettingsScreen() {
    val ctx = LocalContext.current
    val settings = remember { AppGraph.get(ctx).settings }
    var url by remember { mutableStateOf(settings.serverUrl) }
    var token by remember { mutableStateOf(settings.token) }
    var showToken by remember { mutableStateOf(false) }
    var adapter by remember { mutableStateOf(settings.adapterAddress) }
    var simulated by remember { mutableStateOf(settings.simulated) }
    var urlError by remember { mutableStateOf(false) }
    var saved by remember { mutableStateOf(false) }
    val devices = remember { bondedDevices(ctx) }

    Column(
        Modifier.verticalScroll(rememberScrollState()).padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        OutlinedTextField(
            value = url,
            onValueChange = { url = it; urlError = false; saved = false },
            label = { Text("URL del servidor") },
            isError = urlError,
            supportingText = { if (urlError) Text("La URL debe empezar por https:// o http://") },
            singleLine = true,
            modifier = Modifier.fillMaxWidth(),
        )
        OutlinedTextField(
            value = token,
            onValueChange = { token = it; saved = false },
            label = { Text("Token") },
            singleLine = true,
            visualTransformation = if (showToken) VisualTransformation.None else PasswordVisualTransformation(),
            trailingIcon = { TextButton(onClick = { showToken = !showToken }) { Text(if (showToken) "Ocultar" else "Mostrar") } },
            modifier = Modifier.fillMaxWidth(),
        )
        Text("Adaptador OBD", style = MaterialTheme.typography.titleMedium)
        when {
            devices == null -> Text("Falta el permiso de Bluetooth: concédelo para elegir el adaptador.")
            devices.isEmpty() -> Text("No hay dispositivos Bluetooth emparejados.")
            else -> devices.forEach { d ->
                Row(
                    Modifier.fillMaxWidth().selectable(selected = adapter == d.address, onClick = { adapter = d.address; saved = false }),
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    RadioButton(selected = adapter == d.address, onClick = { adapter = d.address; saved = false })
                    Text("${d.name} (${d.address})")
                }
            }
        }
        Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.SpaceBetween) {
            Text("Modo simulado")
            Switch(checked = simulated, onCheckedChange = { simulated = it; saved = false })
        }
        Button(onClick = {
            if (!Formatters.isValidUrl(url)) {
                urlError = true
            } else {
                settings.serverUrl = url.trim()
                settings.token = token.trim()
                settings.adapterAddress = adapter
                settings.simulated = simulated
                saved = true
            }
        }) { Text("Guardar") }
        if (saved) Text("Guardado")
    }
}
