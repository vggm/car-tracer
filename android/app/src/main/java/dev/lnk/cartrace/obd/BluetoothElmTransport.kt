package dev.lnk.cartrace.obd

import android.annotation.SuppressLint
import android.bluetooth.BluetoothManager
import android.bluetooth.BluetoothSocket
import android.content.Context
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.coroutineScope
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.runInterruptible
import java.io.IOException
import java.io.InputStream
import java.util.UUID
import java.util.concurrent.atomic.AtomicBoolean

/** Reads bytes until the ELM prompt `>` (included). Throws IOException on EOF. */
internal fun readUntilPrompt(input: InputStream): String {
    val sb = StringBuilder()
    while (true) {
        val b = input.read()
        if (b < 0) throw IOException("stream closed")
        sb.append(b.toChar())
        if (b == '>'.code) return sb.toString()
    }
}

/**
 * Cancels discovery as a connect-speed optimisation. cancelDiscovery needs BLUETOOTH_SCAN on API 31+,
 * which the app does not declare (it never starts discovery), so a SecurityException is ignored.
 */
internal fun cancelDiscoveryBestEffort(cancel: () -> Boolean): Boolean =
    try {
        cancel()
    } catch (_: SecurityException) {
        false
    }

/** Classic Bluetooth SPP transport. Needs BLUETOOTH_CONNECT granted at runtime. */
@SuppressLint("MissingPermission")
class BluetoothElmTransport(context: Context, private val address: String) : ElmTransport {
    private val manager = context.applicationContext.getSystemService(BluetoothManager::class.java)

    @Volatile
    private var socket: BluetoothSocket? = null

    override suspend fun open() {
        try {
            guarded(timeoutMs = null) {
                val adapter = manager?.adapter ?: throw IOException("no bluetooth adapter")
                if (!adapter.isEnabled) throw IOException("bluetooth disabled")
                val s = adapter.getRemoteDevice(address).createRfcommSocketToServiceRecord(SPP_UUID)
                socket = s
                cancelDiscoveryBestEffort { adapter.cancelDiscovery() }
                s.connect()
            }
        } catch (e: SecurityException) {
            close()
            throw IOException("bluetooth permission denied: ${e.message}", e)
        } catch (e: IllegalArgumentException) {
            close()
            throw IOException("invalid address $address", e)
        } catch (e: IOException) {
            close()
            throw e
        }
    }

    override suspend fun command(cmd: String, timeoutMs: Long): String {
        val s = socket ?: throw IOException("not open")
        return guarded(timeoutMs, cmd) {
            s.outputStream.write((cmd + "\r").toByteArray(Charsets.US_ASCII))
            s.outputStream.flush()
            readUntilPrompt(s.inputStream)
        }
    }

    /**
     * Runs a blocking socket call. BluetoothSocket reads/connects ignore Thread.interrupt, so a
     * watchdog closes the socket from outside: on timeout, or if the caller is cancelled.
     */
    private suspend fun <T> guarded(timeoutMs: Long?, what: String? = null, block: () -> T): T {
        val timedOut = AtomicBoolean(false)
        val finished = AtomicBoolean(false)
        try {
            return coroutineScope {
                val watchdog = launch {
                    try {
                        if (timeoutMs != null) {
                            delay(timeoutMs)
                            timedOut.set(true)
                            close()
                        }
                        awaitCancellationForever()
                    } catch (e: CancellationException) {
                        if (!finished.get()) close()
                        throw e
                    }
                }
                try {
                    runInterruptible(Dispatchers.IO) { block() }
                } finally {
                    finished.set(true)
                    watchdog.cancel()
                }
            }
        } catch (e: IOException) {
            if (timedOut.get()) throw IOException("timeout after ${timeoutMs}ms" + (what?.let { " waiting for $it" } ?: ""), e)
            throw e
        }
    }

    private suspend fun awaitCancellationForever(): Nothing = kotlinx.coroutines.awaitCancellation()

    override fun close() {
        val s = socket
        socket = null
        try { s?.close() } catch (_: IOException) {}
    }

    companion object {
        val SPP_UUID: UUID = UUID.fromString("00001101-0000-1000-8000-00805F9B34FB")
    }
}
