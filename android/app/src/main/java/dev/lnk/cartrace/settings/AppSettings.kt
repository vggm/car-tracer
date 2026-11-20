package dev.lnk.cartrace.settings

import android.content.SharedPreferences
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow

data class SettingsSnapshot(
    val serverUrl: String,
    val token: String,
    val adapterAddress: String,
    val simulated: Boolean,
    val deviceId: String,
    val obdProtocol: String,
)

/** App settings over SharedPreferences; getters always read the current stored value. */
class AppSettings(private val prefs: SharedPreferences) {
    private val _changes = MutableStateFlow(snapshot())
    val changes: StateFlow<SettingsSnapshot> = _changes.asStateFlow()

    var serverUrl: String
        get() = prefs.getString(K_URL, "") ?: ""
        set(v) = put { putString(K_URL, v) }
    var token: String
        get() = prefs.getString(K_TOKEN, "") ?: ""
        set(v) = put { putString(K_TOKEN, v) }
    var adapterAddress: String
        get() = prefs.getString(K_ADAPTER, "") ?: ""
        set(v) = put { putString(K_ADAPTER, v) }
    var simulated: Boolean
        get() = prefs.getBoolean(K_SIM, false)
        set(v) = put { putBoolean(K_SIM, v) }
    var deviceId: String
        get() = prefs.getString(K_DEVICE, DEFAULT_DEVICE_ID) ?: DEFAULT_DEVICE_ID
        set(v) = put { putString(K_DEVICE, v) }

    var obdProtocol: String
        get() = prefs.getString(K_PROTOCOL, DEFAULT_PROTOCOL) ?: DEFAULT_PROTOCOL
        set(v) = put { putString(K_PROTOCOL, v) }

    fun snapshot() = SettingsSnapshot(serverUrl, token, adapterAddress, simulated, deviceId, obdProtocol)

    private inline fun put(block: SharedPreferences.Editor.() -> Unit) {
        prefs.edit().apply(block).commit()
        _changes.value = snapshot()
    }

    companion object {
        const val DEFAULT_PROTOCOL = "0"
        const val DEFAULT_DEVICE_ID = "junsun-307"
        private const val K_URL = "server_url"
        private const val K_TOKEN = "token"
        private const val K_ADAPTER = "adapter_address"
        private const val K_SIM = "simulated"
        private const val K_PROTOCOL = "obd_protocol"
        private const val K_DEVICE = "device_id"
    }
}
