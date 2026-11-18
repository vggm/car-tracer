package dev.lnk.cartrace.service

import android.content.pm.ServiceInfo
import org.junit.Assert.assertEquals
import org.junit.Test

class ForegroundTypesTest {
    @Test fun locationOnlyWithoutBluetooth() {
        assertEquals(ServiceInfo.FOREGROUND_SERVICE_TYPE_LOCATION, foregroundTypes(false))
    }

    @Test fun addsConnectedDeviceWithBluetooth() {
        assertEquals(
            ServiceInfo.FOREGROUND_SERVICE_TYPE_LOCATION or ServiceInfo.FOREGROUND_SERVICE_TYPE_CONNECTED_DEVICE,
            foregroundTypes(true),
        )
    }
}
