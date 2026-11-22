package dev.lnk.cartrace.diag

import dev.lnk.cartrace.obd.ObdState
import org.junit.Assert.assertEquals
import org.junit.Test

class HealthSnapshotTest {
    @Test
    fun valuesUseSpecKeysAndOmitNulls() {
        val v = healthValues(
            HealthInputs(
                queuePending = 5, queueDroppedTotal = 2, uploadOkAgeS = 30, uploadFailures = 1,
                gpsEnabled = true, gpsPermission = true, gpsFixAgeS = 4, gpsAccM = 6.5,
                obdState = 2, btEnabled = false, net = 1, batteryPct = 80, charging = true,
                storageFreeMb = 1024, uptimeS = 100, serviceUptimeS = 50,
            )
        )
        assertEquals(
            setOf(
                "queue_pending", "queue_dropped_total", "upload_ok_age_s", "upload_failures",
                "gps_enabled", "gps_permission", "gps_fix_age_s", "gps_acc_m", "obd_state",
                "bt_enabled", "net", "battery_pct", "charging", "storage_free_mb", "uptime_s",
                "service_uptime_s",
            ),
            v.keys,
        )
        assertEquals(6.5, v["gps_acc_m"]!!, 0.0)
        assertEquals(5.0, v["queue_pending"]!!, 0.0)

        val partial = healthValues(HealthInputs(queuePending = 1, gpsAccM = null))
        assertEquals(setOf("queue_pending"), partial.keys)
        assertEquals(emptyMap<String, Double>(), healthValues(HealthInputs()))
    }

    @Test
    fun obdStateCodes() {
        assertEquals(0, obdStateCode(null))
        assertEquals(1, obdStateCode(ObdState.Connecting))
        assertEquals(2, obdStateCode(ObdState.Connected("6")))
        assertEquals(3, obdStateCode(ObdState.Retrying("x", 1000)))
    }

    @Test
    fun booleansAsZeroOne() {
        val v = healthValues(
            HealthInputs(gpsEnabled = true, gpsPermission = false, btEnabled = true, charging = false)
        )
        assertEquals(1.0, v["gps_enabled"]!!, 0.0)
        assertEquals(0.0, v["gps_permission"]!!, 0.0)
        assertEquals(1.0, v["bt_enabled"]!!, 0.0)
        assertEquals(0.0, v["charging"]!!, 0.0)
    }
}
