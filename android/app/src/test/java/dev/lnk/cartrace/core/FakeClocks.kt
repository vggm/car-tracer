package dev.lnk.cartrace.core

class FakeClocks(
    var elapsed: Long = 0,
    var uptime: Long = 0,
    var wall: Long = 0,
    var boot: Int = 1,
) : Clocks {
    override fun elapsedMs() = elapsed
    override fun uptimeMs() = uptime
    override fun wallMs() = wall
    override fun bootCount() = boot
}
