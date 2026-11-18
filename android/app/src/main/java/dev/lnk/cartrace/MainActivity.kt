package dev.lnk.cartrace

import android.app.Activity
import android.content.ActivityNotFoundException
import android.content.Context
import android.content.ContextWrapper
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
import androidx.compose.material3.TextButton
import androidx.compose.runtime.mutableStateOf
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

private const val K_SKIPPED = "skipped_steps"

private fun openWithFallbacks(ctx: Context, vararg intents: Intent) {
    for (i in intents) {
        try {
            ctx.startActivity(i)
            return
        } catch (e: ActivityNotFoundException) {
            // try the next fallback
        } catch (e: SecurityException) {
            // try the next fallback
        }
    }
}

private fun appDetails(ctx: Context) =
    Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS, Uri.parse("package:${ctx.packageName}"))

@Composable
private fun App() {
    val ctx = LocalContext.current
    val activity = remember { ctx.findActivity() }
    val settings = remember { AppGraph.get(ctx).settings }
    val prefs = remember { ctx.getSharedPreferences(UI_PREFS, Context.MODE_PRIVATE) }
    var tick by remember { mutableIntStateOf(0) }  // bump to recompute onboarding state
    var showSettings by rememberSaveable { mutableStateOf(false) }
    var denied by remember { mutableStateOf(setOf<String>()) }
    var requested by remember { mutableStateOf<String?>(null) }

    val granted = remember(tick) {
        RUNTIME_PERMISSIONS.filterTo(mutableSetOf()) {
            ctx.checkSelfPermission(it) == PackageManager.PERMISSION_GRANTED
        }
    }
    val skipped = remember(tick) {
        prefs.getStringSet(K_SKIPPED, emptySet()).orEmpty().mapNotNull { n ->
            OnboardingStep.entries.firstOrNull { it.name == n }
        }.toSet()
    }
    val current = remember(tick) {
        val g = granted.toMutableSet()
        if (prefs.getBoolean(K_AUTOSTART_SEEN, false)) g += Permissions.AUTOSTART_SEEN
        val exempt = ctx.getSystemService(PowerManager::class.java).isIgnoringBatteryOptimizations(ctx.packageName)
        Permissions.nextStep(g, exempt, skipped)
    }

    // Re-evaluate when returning from system settings screens.
    val owner = LocalLifecycleOwner.current
    DisposableEffect(owner) {
        val obs = LifecycleEventObserver { _, e -> if (e == Lifecycle.Event.ON_RESUME) tick++ }
        owner.lifecycle.addObserver(obs)
        onDispose { owner.lifecycle.removeObserver(obs) }
    }

    val launcher = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) { ok ->
        val p = requested
        if (!ok && p != null && activity != null && !activity.shouldShowRequestPermissionRationale(p)) {
            denied = denied + p
        }
        tick++
    }

    // The activity is visible here, so a location FGS may start (Android 14), but only with the required permissions.
    val canStart = Permissions.canStartService(granted, settings.simulated)
    LaunchedEffect(canStart) {
        if (canStart) ctx.startForegroundService(Intent(ctx, TelemetryService::class.java))
    }

    when {
        current == null -> Tabs()
        showSettings -> Column(Modifier.statusBarsPadding()) {
            TextButton(onClick = { showSettings = false }) { Text("Volver") }
            SettingsScreen()
        }
        else -> OnboardingScreen(
            step = current,
            permanentlyDenied = Permissions.permissionFor(current)?.let { it in denied } == true,
            onAction = {
                val perm = Permissions.permissionFor(current)
                when {
                    perm != null -> {
                        requested = perm
                        launcher.launch(perm)
                    }
                    current == OnboardingStep.BATTERY -> openWithFallbacks(
                        ctx,
                        Intent(Settings.ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS, Uri.parse("package:${ctx.packageName}")),
                        Intent(Settings.ACTION_IGNORE_BATTERY_OPTIMIZATION_SETTINGS),
                        appDetails(ctx),
                    )
                    else -> {
                        prefs.edit().putBoolean(K_AUTOSTART_SEEN, true).apply()
                        tick++
                    }
                }
            },
            onOpenAppSettings = { openWithFallbacks(ctx, appDetails(ctx)) },
            onSkip = if (current in Permissions.SKIPPABLE) {
                {
                    prefs.edit().putStringSet(K_SKIPPED, (skipped + current).map { it.name }.toSet()).apply()
                    tick++
                }
            } else null,
            onOpenSettings = { showSettings = true },
        )
    }
}

private fun Context.findActivity(): Activity? {
    var c = this
    while (c is ContextWrapper) {
        if (c is Activity) return c
        c = c.baseContext
    }
    return null
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
