package dev.lnk.cartrace.core

import android.content.Context
import android.os.SystemClock
import android.provider.Settings

interface Clocks {
    fun elapsedMs(): Long
    fun uptimeMs(): Long
    fun wallMs(): Long
    fun bootCount(): Int
}

data class Stamp(val bootCount: Int, val elapsedMs: Long, val wallMs: Long)

fun Clocks.stamp(): Stamp = Stamp(bootCount(), elapsedMs(), wallMs())

class AndroidClocks(context: Context) : Clocks {
    private val resolver = context.applicationContext.contentResolver
    override fun elapsedMs() = SystemClock.elapsedRealtime()
    override fun uptimeMs() = SystemClock.uptimeMillis()
    override fun wallMs() = System.currentTimeMillis()
    override fun bootCount() = Settings.Global.getInt(resolver, Settings.Global.BOOT_COUNT, 0)
}
