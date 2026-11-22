package dev.lnk.cartrace.service

/** Pure "no GPS fix for too long" detector: [tick] is true once per streak without fixes. */
class GpsNoFixWatcher(
    private val nowMs: () -> Long,
    private val thresholdMs: Long = 120_000,
) {
    /** Reference for the "no fix since" count when there is no newer fix. */
    @Volatile private var startMs = nowMs()
    @Volatile private var lastFixMs: Long? = null
    @Volatile private var reported = false

    fun onFix() {
        lastFixMs = nowMs()
        reported = false
    }

    /** After deep sleep the monotonic clock jumped: count "no fix" from now (last fix kept for [fixAgeS]). */
    fun onResume() {
        startMs = nowMs()
        reported = false
    }

    fun tick(): Boolean {
        val ref = maxOf(lastFixMs ?: startMs, startMs)
        if (reported || nowMs() - ref <= thresholdMs) return false
        reported = true
        return true
    }

    /** Seconds since the last fix, or null if there has been none. */
    fun fixAgeS(): Long? = lastFixMs?.let { (nowMs() - it) / 1000 }
}
