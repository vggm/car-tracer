package dev.lnk.cartrace.service

import android.content.pm.ServiceInfo

/**
 * Foreground service types allowed right now. With targetSdk 34 the connectedDevice type is
 * only accepted when BLUETOOTH_CONNECT is granted, so it is added only then.
 */
fun foregroundTypes(bluetoothConnectGranted: Boolean): Int {
    val location = ServiceInfo.FOREGROUND_SERVICE_TYPE_LOCATION
    return if (bluetoothConnectGranted) location or ServiceInfo.FOREGROUND_SERVICE_TYPE_CONNECTED_DEVICE else location
}
