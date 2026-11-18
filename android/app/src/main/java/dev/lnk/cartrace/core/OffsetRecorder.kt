package dev.lnk.cartrace.core

import dev.lnk.cartrace.queue.BootOffset

/**
 * Decides which GPS fixes may set the boot's time offset and whether it is persisted.
 * Simulated fixes never count; with an unknown boot count (<= 0) offsets stay in memory only,
 * because several boots would otherwise share one key.
 */
class OffsetRecorder(
    private val clock: SessionClock,
    private val save: suspend (BootOffset) -> Unit,
) {
    suspend fun onFix(boot: Int, utcMs: Long, elapsedMs: Long, simulated: Boolean) {
        if (simulated) return
        if (!clock.onGpsFix(boot, utcMs, elapsedMs)) return
        if (boot > 0) save(BootOffset(boot, utcMs - elapsedMs))
    }

    companion object {
        /** Persisted offsets that are safe to use: those keyed by a real boot count. */
        fun usablePersisted(rows: List<BootOffset>): Map<Int, Long> =
            rows.filter { it.bootCount > 0 }.associate { it.bootCount to it.offsetMs }
    }
}
