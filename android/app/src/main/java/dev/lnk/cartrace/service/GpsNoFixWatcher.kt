package dev.lnk.cartrace.service

/** Pure "no GPS fix for too long" detector: [tick] is true once per streak without fixes. */
class GpsNoFixWatcher(
    private val nowMs: () -> Long,
    private val thresholdMs: Long = 120_000,
) {
    private val startMs = nowMs()
    @Volatile private var lastFixMs: Long? = null
    @Volatile private var reported = false

    fun onFix() {
        lastFixMs = nowMs()
        reported = false
    }

    fun tick(): Boolean {
        val ref = lastFixMs ?: startMs
        if (reported || nowMs() - ref <= thresholdMs) return false
        reported = true
        return true
    }

    /** Seconds since the last fix, or null if there has been none. */
    fun fixAgeS(): Long? = lastFixMs?.let { (nowMs() - it) / 1000 }
}
