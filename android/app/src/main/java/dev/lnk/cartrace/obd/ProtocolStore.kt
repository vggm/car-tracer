package dev.lnk.cartrace.obd

import android.content.SharedPreferences

/** Remembers the OBD protocol number (ATDPN without the auto "A") found for each adapter address. */
interface ProtocolStore {
    fun get(address: String): String?
    fun put(address: String, protocol: String)
}

object NoProtocolStore : ProtocolStore {
    override fun get(address: String): String? = null
    override fun put(address: String, protocol: String) {}
}

class PrefsProtocolStore(private val prefs: SharedPreferences) : ProtocolStore {
    override fun get(address: String): String? = prefs.getString(KEY + address, null)
    override fun put(address: String, protocol: String) {
        prefs.edit().putString(KEY + address, protocol).apply()
    }

    private companion object { const val KEY = "obd_protocol_" }
}
