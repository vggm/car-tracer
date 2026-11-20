package dev.lnk.cartrace.service

/** Tells whether the car is moving, from the latest GPS fix and a monotonic clock. */
class MotionTracker(private val elapsedMs: () -> Long) {
    private var speedMps: Double? = null
    private var fixAtMs = 0L

    @Synchronized
    fun onFix(speedMps: Double?) {
        this.speedMps = speedMps
        fixAtMs = elapsedMs()
    }

    @Synchronized
    fun isMoving(): Boolean {
        val s = speedMps ?: return false
        return s >= MOVING_MIN_MPS && elapsedMs() - fixAtMs < FIX_FRESH_MS
    }

    companion object {
        /** 5 km/h. */
        const val MOVING_MIN_MPS = 1.389
        const val FIX_FRESH_MS = 15_000L
    }
}
