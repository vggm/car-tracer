package dev.lnk.cartrace.obd

/** Pure parsing of ELM327 text responses. No function here throws. */
object ElmParser {
    private val ERRORS = listOf(
        "NODATA", "UNABLETOCONNECT", "STOPPED", "CANERROR", "BUSERROR", "ERROR",
    )
    private val VOLTAGE = Regex("(\\d+(?:\\.\\d+)?)V")

    /** Splits into lines, removes spaces, prompt, SEARCHING.../BUS INIT noise and empty lines. */
    fun clean(raw: String): List<String> =
        raw.split('\r', '\n')
            .map { it.replace(">", "").filter { c -> !c.isWhitespace() }.uppercase() }
            .filter { it.isNotEmpty() && !it.startsWith("SEARCHING") && !it.startsWith("BUSINIT") }

    fun value(pid: Pid, raw: String): Double? = try {
        val prefix = "41" + pid.cmd.substring(2)
        val needed = if (pid in TWO_BYTE) 2 else 1
        clean(raw).firstNotNullOfOrNull { line ->
            if (!line.startsWith(prefix)) return@firstNotNullOfOrNull null
            val bytes = hexBytes(line.substring(prefix.length)) ?: return@firstNotNullOfOrNull null
            if (bytes.size < needed) null else compute(pid, bytes)
        }
    } catch (e: Exception) {
        null
    }

    private val TWO_BYTE = setOf(Pid.RPM, Pid.FUEL_RATE)

    private fun compute(pid: Pid, b: List<Int>): Double = when (pid) {
        Pid.RPM -> (256 * b[0] + b[1]) / 4.0
        Pid.FUEL_RATE -> (256 * b[0] + b[1]) / 20.0
        Pid.SPEED, Pid.INTAKE -> b[0].toDouble()
        Pid.COOLANT -> b[0] - 40.0
        Pid.LOAD, Pid.THROTTLE -> b[0] * 100.0 / 255.0
    }

    fun supportedPids(responses: List<String>): Set<String> {
        val result = linkedSetOf<String>()
        try {
            for (raw in responses) for (line in clean(raw)) {
                if (!line.startsWith("41") || line.length < 12) continue
                val bytes = hexBytes(line.substring(2, 12)) ?: continue
                val base = bytes[0]
                for (i in 0 until 32) {
                    val byteIdx = 1 + i / 8
                    if (bytes[byteIdx] and (0x80 shr (i % 8)) != 0) {
                        result += "01%02X".format(base + i + 1)
                    }
                }
            }
        } catch (e: Exception) {
            // best effort
        }
        return result
    }

    fun dtcs(raw: String, mode: Char): List<String> {
        val prefix = when (mode) {
            '3' -> "43"
            '7' -> "47"
            else -> return emptyList()
        }
        return try {
            clean(raw).filter { it.startsWith(prefix) }.flatMap { line ->
                val body = line.substring(2)
                body.chunked(4).filter { it.length == 4 && it != "0000" }
                    .mapNotNull { hexBytes(it)?.let { (a, b) -> decodeDtc(a, b) } }
            }
        } catch (e: Exception) {
            emptyList()
        }
    }

    private fun decodeDtc(a: Int, b: Int): String {
        val letter = "PCBU"[a shr 6]
        val second = (a shr 4) and 0x3
        return "%c%d%X%02X".format(letter, second, a and 0xF, b)
    }

    fun voltage(raw: String): Double? = try {
        clean(raw).firstNotNullOfOrNull { VOLTAGE.find(it)?.groupValues?.get(1)?.toDoubleOrNull() }
    } catch (e: Exception) {
        null
    }

    /** "BUS INIT: ...ERROR" is dropped by [clean] as noise, so it has to be detected on the raw text. */
    fun isBusInitError(raw: String): Boolean =
        raw.split('\r', '\n')
            .map { it.filter { c -> !c.isWhitespace() }.uppercase() }
            .any { it.startsWith("BUSINIT") && it.contains("ERROR") }

    fun isError(raw: String): Boolean =
        isBusInitError(raw) || clean(raw).any { line -> line == "?" || ERRORS.any { line.contains(it) } }

    private fun hexBytes(hex: String): List<Int>? {
        if (hex.length % 2 != 0) return null
        return hex.chunked(2).map { it.toIntOrNull(16) ?: return null }
    }
}
