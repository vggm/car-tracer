package dev.lnk.cartrace.obd

import android.annotation.SuppressLint
import android.bluetooth.BluetoothManager
import android.bluetooth.BluetoothSocket
import android.content.Context
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.runInterruptible
import kotlinx.coroutines.withContext
import kotlinx.coroutines.withTimeoutOrNull
import java.io.IOException
import java.util.UUID

/** Classic Bluetooth SPP transport. Needs BLUETOOTH_CONNECT granted at runtime. */
@SuppressLint("MissingPermission")
class BluetoothElmTransport(context: Context, private val address: String) : ElmTransport {
    private val manager = context.applicationContext.getSystemService(BluetoothManager::class.java)
    private var socket: BluetoothSocket? = null

    override suspend fun open() {
        withContext(Dispatchers.IO) {
            try {
                val adapter = manager?.adapter ?: throw IOException("no bluetooth adapter")
                if (!adapter.isEnabled) throw IOException("bluetooth disabled")
                val s = adapter.getRemoteDevice(address).createRfcommSocketToServiceRecord(SPP_UUID)
                socket = s
                adapter.cancelDiscovery()
                s.connect()
            } catch (e: SecurityException) {
                close()
                throw IOException("missing BLUETOOTH_CONNECT permission", e)
            } catch (e: IllegalArgumentException) {
                close()
                throw IOException("invalid address $address", e)
            } catch (e: IOException) {
                close()
                throw e
            }
        }
    }

    override suspend fun command(cmd: String, timeoutMs: Long): String {
        val s = socket ?: throw IOException("not open")
        val result = withTimeoutOrNull(timeoutMs) {
            runInterruptible(Dispatchers.IO) {
                s.outputStream.write((cmd + "\r").toByteArray(Charsets.US_ASCII))
                s.outputStream.flush()
                val sb = StringBuilder()
                while (true) {
                    val b = s.inputStream.read()
                    if (b < 0) throw IOException("stream closed")
                    sb.append(b.toChar())
                    if (b == '>'.code) break
                }
                sb.toString()
            }
        }
        if (result == null) {
            close() // unblocks a stuck read
            throw IOException("timeout waiting for response to $cmd")
        }
        return result
    }

    override fun close() {
        try { socket?.close() } catch (_: IOException) {}
        socket = null
    }

    companion object {
        val SPP_UUID: UUID = UUID.fromString("00001101-0000-1000-8000-00805F9B34FB")
    }
}
