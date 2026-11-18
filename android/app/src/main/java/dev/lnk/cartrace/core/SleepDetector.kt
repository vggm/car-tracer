package dev.lnk.cartrace.core

/** Detects that the device slept: elapsedRealtime advances while uptime does not. */
class SleepDetector(private val clocks: Clocks, private val thresholdMs: Long = 60_000) {
    private var lastElapsed = -1L
    private var lastUptime = -1L

    fun tick(): Boolean {
        val e = clocks.elapsedMs()
        val u = clocks.uptimeMs()
        val first = lastElapsed < 0
        val slept = !first && (e - lastElapsed) - (u - lastUptime) > thresholdMs
        lastElapsed = e
        lastUptime = u
        return slept
    }
}
