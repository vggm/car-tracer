package dev.lnk.cartrace

import android.content.Intent
import android.content.pm.PackageManager
import android.net.Uri
import android.os.Bundle
import android.os.PowerManager
import android.provider.Settings
import androidx.activity.ComponentActivity
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Tab
import androidx.compose.material3.TabRow
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalLifecycleOwner
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleEventObserver
import dev.lnk.cartrace.service.AppGraph
import dev.lnk.cartrace.service.TelemetryService
import dev.lnk.cartrace.ui.OnboardingScreen
import dev.lnk.cartrace.ui.OnboardingStep
import dev.lnk.cartrace.ui.Permissions
import dev.lnk.cartrace.ui.SettingsScreen
import dev.lnk.cartrace.ui.StatusScreen

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent { MaterialTheme { Surface(Modifier.fillMaxSize()) { App() } } }
    }
}

private const val UI_PREFS = "car-trace-ui"
private const val K_AUTOSTART_SEEN = "autostart_seen"

private val RUNTIME_PERMISSIONS = listOf(
    Permissions.FINE_LOCATION,
    Permissions.BACKGROUND_LOCATION,
    Permissions.BLUETOOTH_CONNECT,
    Permissions.POST_NOTIFICATIONS,
)

@Composable
private fun App() {
    val ctx = LocalContext.current
    val prefs = remember { ctx.getSharedPreferences(UI_PREFS, android.content.Context.MODE_PRIVATE) }
    var tick by remember { mutableIntStateOf(0) }  // bump to recompute the onboarding step

    fun step(): OnboardingStep? {
        val granted = RUNTIME_PERMISSIONS.filterTo(mutableSetOf()) {
            ctx.checkSelfPermission(it) == PackageManager.PERMISSION_GRANTED
        }
        if (prefs.getBoolean(K_AUTOSTART_SEEN, false)) granted += Permissions.AUTOSTART_SEEN
        val exempt = ctx.getSystemService(PowerManager::class.java).isIgnoringBatteryOptimizations(ctx.packageName)
        return Permissions.nextStep(granted, exempt)
    }

    // Re-evaluate when returning from system settings screens.
    val owner = LocalLifecycleOwner.current
    DisposableEffect(owner) {
        val obs = LifecycleEventObserver { _, e -> if (e == Lifecycle.Event.ON_RESUME) tick++ }
        owner.lifecycle.addObserver(obs)
        onDispose { owner.lifecycle.removeObserver(obs) }
    }

    val launcher = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) { tick++ }
    val current = remember(tick) { step() }

    if (current != null) {
        OnboardingScreen(current) {
            when (current) {
                OnboardingStep.FINE_LOCATION -> launcher.launch(Permissions.FINE_LOCATION)
                // Android 11+: the system sends the user to settings ("Permitir siempre").
                OnboardingStep.BACKGROUND_LOCATION -> launcher.launch(Permissions.BACKGROUND_LOCATION)
                OnboardingStep.BLUETOOTH_CONNECT -> launcher.launch(Permissions.BLUETOOTH_CONNECT)
                OnboardingStep.POST_NOTIFICATIONS -> launcher.launch(Permissions.POST_NOTIFICATIONS)
                OnboardingStep.BATTERY -> ctx.startActivity(
                    Intent(Settings.ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS, Uri.parse("package:${ctx.packageName}")),
                )
                OnboardingStep.AUTOSTART_INFO -> {
                    prefs.edit().putBoolean(K_AUTOSTART_SEEN, true).apply()
                    tick++
                }
            }
        }
    } else {
        // Onboarding done: the activity is visible, so a location FGS may start (Android 14).
        LaunchedEffect(Unit) { ctx.startForegroundService(Intent(ctx, TelemetryService::class.java)) }
        Tabs()
    }
}

@Composable
private fun Tabs() {
    var tab by rememberSaveable { mutableIntStateOf(0) }
    Column(Modifier.statusBarsPadding()) {
        TabRow(selectedTabIndex = tab) {
            Tab(selected = tab == 0, onClick = { tab = 0 }, text = { Text("Estado") })
            Tab(selected = tab == 1, onClick = { tab = 1 }, text = { Text("Ajustes") })
        }
        if (tab == 0) StatusScreen() else SettingsScreen()
    }
}
