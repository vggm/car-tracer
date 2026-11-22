package dev.lnk.cartrace.sim

import dev.lnk.cartrace.obd.ElmTransport
import java.util.Locale
import kotlin.math.PI
import kotlin.math.sin

/** Pretends to be an ELM327 with plausible, time-varying values. 015E answers NO DATA. */
class FakeElmTransport(private val nowMs: () -> Long = System::currentTimeMillis) : ElmTransport {
    private var t0 = 0L

    override suspend fun open() { t0 = nowMs() }

    override suspend fun command(cmd: String, timeoutMs: Long): String {
        val t = (nowMs() - t0) / 1000.0
        val body = when (cmd.uppercase().replace(" ", "")) {
            "ATZ", "ATWS", "ATI" -> "ELM327 v1.5"
            "AT@1" -> "OBDII to RS232 Interpreter"
            "ATDP" -> "AUTO, ISO 15765-4 (CAN 11/500)"
            "ATPPS" -> "00:FF F:68"
            "ATFI" -> "BUS INIT: OK"
            "ATDPN" -> "A6"
            "ATRV" -> "%.1fV".format(Locale.US, 13.8 - 0.4 * (0.5 + 0.5 * sin(t / 120 * 2 * PI)))
            "0100" -> "41 00 18 38 80 01"
            "0120" -> "41 20 00 00 00 01"
            "0140" -> "41 40 00 00 00 00"
            "03" -> "43 00 00 00 00 00 00"
            "07" -> "47 00 00 00 00 00 00"
            "010C" -> {
                val rpm = 800 + 1700 * (0.5 + 0.5 * sin(t / 20 * 2 * PI))
                "41 0C " + hex2((rpm * 4).toInt())
            }
            "010D" -> "41 0D " + hex1((50 + 30 * sin(t / 60 * 2 * PI)).toInt())
            "0105" -> "41 05 " + hex1((minOf(88.0, 20 + t / 4) + 40).toInt())
            "010B" -> "41 0B " + hex1((35 + 20 * (0.5 + 0.5 * sin(t / 20 * 2 * PI))).toInt())
            "0104" -> "41 04 " + hex1((255 * (0.25 + 0.15 * sin(t / 15 * 2 * PI))).toInt())
            "0111" -> "41 11 " + hex1((255 * (0.15 + 0.1 * sin(t / 15 * 2 * PI))).toInt())
            "015E" -> "NO DATA"
            else -> if (cmd.startsWith("AT", ignoreCase = true)) "OK" else "?"
        }
        return "$body\r\r>"
    }

    override fun close() {}

    private fun hex1(v: Int) = "%02X".format(Locale.US, v.coerceIn(0, 255))
    private fun hex2(v: Int) = "%02X %02X".format(Locale.US, (v shr 8) and 0xFF, v and 0xFF)
}
