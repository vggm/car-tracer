package dev.lnk.cartrace.gps

data class GpsFix(
    val utcMs: Long,
    val lat: Double,
    val lon: Double,
    val accM: Double,
    val speedMps: Double?,
    val bearing: Double?,
    val altM: Double?,
)

interface GpsSource {
    fun start(onFix: (GpsFix) -> Unit)
    fun stop()
}
