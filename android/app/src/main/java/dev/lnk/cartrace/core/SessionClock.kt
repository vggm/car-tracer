package dev.lnk.cartrace.core

import dev.lnk.cartrace.BuildConfig
import java.util.concurrent.ConcurrentHashMap

sealed interface Resolution {
    data class Ts(val utcMs: Long) : Resolution
    data object Wait : Resolution
    data object Drop : Resolution
}

/** Resolves record timestamps to UTC (spec 6.3), robust to a wrong system clock at boot. */
class SessionClock(private val minWallMs: Long = BuildConfig.BUILD_TIME_MS) {
    private val offsets = ConcurrentHashMap<Int, Long>()

    /**
     * Keeps the first plausible offset (utc - elapsed) seen for each boot. Fixes earlier than
     * [minWallMs] (GPS week rollover, bogus time) are ignored. True if this fix set the offset.
     */
    fun onGpsFix(bootCount: Int, gpsUtcMs: Long, elapsedMs: Long): Boolean {
        if (gpsUtcMs < minWallMs) return false
        return offsets.putIfAbsent(bootCount, gpsUtcMs - elapsedMs) == null
    }

    fun offsets(): Map<Int, Long> = offsets.toMap()

    fun resolve(stamp: Stamp, offsets: Map<Int, Long>, currentBoot: Int): Resolution {
        offsets[stamp.bootCount]?.let { return Resolution.Ts(stamp.elapsedMs + it) }
        if (stamp.wallMs >= minWallMs) return Resolution.Ts(stamp.wallMs)
        return if (stamp.bootCount == currentBoot) Resolution.Wait else Resolution.Drop
    }
}
