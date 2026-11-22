package dev.lnk.cartrace.diag

import dev.lnk.cartrace.obd.ObdState

/** One nullable field per health key (spec section 6); null means "could not be read". */
data class HealthInputs(
    val queuePending: Long? = null,
    val queueDroppedTotal: Long? = null,
    val uploadOkAgeS: Long? = null,
    val uploadFailures: Long? = null,
    val gpsEnabled: Boolean? = null,
    val gpsPermission: Boolean? = null,
    val gpsFixAgeS: Long? = null,
    val gpsAccM: Double? = null,
    val obdState: Int? = null,
    val btEnabled: Boolean? = null,
    val net: Int? = null,
    val batteryPct: Int? = null,
    val charging: Boolean? = null,
    val storageFreeMb: Long? = null,
    val uptimeS: Long? = null,
    val serviceUptimeS: Long? = null,
)

private fun Boolean.d() = if (this) 1.0 else 0.0

/** Numeric health values keyed as in the spec; null inputs are omitted. */
fun healthValues(i: HealthInputs): Map<String, Double> {
    val m = LinkedHashMap<String, Double>()
    i.queuePending?.let { m["queue_pending"] = it.toDouble() }
    i.queueDroppedTotal?.let { m["queue_dropped_total"] = it.toDouble() }
    i.uploadOkAgeS?.let { m["upload_ok_age_s"] = it.toDouble() }
    i.uploadFailures?.let { m["upload_failures"] = it.toDouble() }
    i.gpsEnabled?.let { m["gps_enabled"] = it.d() }
    i.gpsPermission?.let { m["gps_permission"] = it.d() }
    i.gpsFixAgeS?.let { m["gps_fix_age_s"] = it.toDouble() }
    i.gpsAccM?.let { m["gps_acc_m"] = it }
    i.obdState?.let { m["obd_state"] = it.toDouble() }
    i.btEnabled?.let { m["bt_enabled"] = it.d() }
    i.net?.let { m["net"] = it.toDouble() }
    i.batteryPct?.let { m["battery_pct"] = it.toDouble() }
    i.charging?.let { m["charging"] = it.d() }
    i.storageFreeMb?.let { m["storage_free_mb"] = it.toDouble() }
    i.uptimeS?.let { m["uptime_s"] = it.toDouble() }
    i.serviceUptimeS?.let { m["service_uptime_s"] = it.toDouble() }
    return m
}

/** 0 stopped, 1 connecting, 2 connected, 3 retrying. */
fun obdStateCode(s: ObdState?): Int = when (s) {
    null -> 0
    is ObdState.Connecting -> 1
    is ObdState.Connected -> 2
    is ObdState.Retrying -> 3
}
