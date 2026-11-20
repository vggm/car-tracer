package dev.lnk.cartrace.ui

import android.Manifest
import android.annotation.SuppressLint
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.platform.LocalLifecycleOwner
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleEventObserver
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

private data class Bonded(val name: String, val address: String, val paired: Boolean = true) {
    val label get() = if (paired) "$name ($address)" else "$address (no emparejado)"
}

private val PROTOCOLS = listOf(
    "Automático (recomendado)" to "0",
    "ISO 14230 KWP rápido" to "5",
    "ISO 14230 KWP lento" to "4",
    "ISO 9141-2" to "3",
    "CAN 500 kbps" to "6",
)

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
    var url by rememberSaveable { mutableStateOf(settings.serverUrl) }
    var token by rememberSaveable { mutableStateOf(settings.token) }
    var showToken by rememberSaveable { mutableStateOf(false) }
    var adapter by rememberSaveable { mutableStateOf(settings.adapterAddress) }
    var protocol by rememberSaveable { mutableStateOf(settings.obdProtocol) }
    var simulated by rememberSaveable { mutableStateOf(settings.simulated) }
    var urlError by rememberSaveable { mutableStateOf(false) }
    var saved by remember { mutableStateOf(false) }
    var refresh by remember { mutableIntStateOf(0) }
    val owner = LocalLifecycleOwner.current
    DisposableEffect(owner) {
        val obs = LifecycleEventObserver { _, e -> if (e == Lifecycle.Event.ON_RESUME) refresh++ }
        owner.lifecycle.addObserver(obs)
        onDispose { owner.lifecycle.removeObserver(obs) }
    }
    val btLauncher = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) { refresh++ }
    val devices = remember(refresh) { bondedDevices(ctx) }

    Column(
        Modifier.verticalScroll(rememberScrollState()).padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        OutlinedTextField(
            value = url,
            onValueChange = { url = it; urlError = false; saved = false },
            label = { Text("URL del servidor (ruta completa del ingest)") },
            placeholder = { Text("https://lnk-server.<tailnet>.ts.net/api/v1/ingest") },
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
            devices == null -> {
                Text("Falta el permiso de Bluetooth: concédelo para elegir el adaptador.")
                TextButton(onClick = { btLauncher.launch(Manifest.permission.BLUETOOTH_CONNECT) }) { Text("Conceder Bluetooth") }
            }
            else -> {
                if (devices.isEmpty()) Text("No hay dispositivos Bluetooth emparejados.")
                val shown = if (adapter.isNotBlank() && devices.none { it.address == adapter }) {
                    devices + Bonded(adapter, adapter, paired = false)
                } else devices
                shown.forEach { d ->
                Row(
                    Modifier.fillMaxWidth().selectable(selected = adapter == d.address, onClick = { adapter = d.address; saved = false }),
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    RadioButton(selected = adapter == d.address, onClick = { adapter = d.address; saved = false })
                    Text(d.label)
                }
                }
            }
        }
        Text("Protocolo OBD", style = MaterialTheme.typography.titleMedium)
        PROTOCOLS.forEach { (label, value) ->
            Row(
                Modifier.fillMaxWidth().selectable(selected = protocol == value, onClick = { protocol = value; saved = false }),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                RadioButton(selected = protocol == value, onClick = { protocol = value; saved = false })
                Text(label)
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
                settings.obdProtocol = protocol
                settings.simulated = simulated
                saved = true
            }
        }) { Text("Guardar") }
        if (saved) Text("Guardado")
    }
}
