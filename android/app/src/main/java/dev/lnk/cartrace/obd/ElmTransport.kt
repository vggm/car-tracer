package dev.lnk.cartrace.obd

/** Text channel to an ELM327. Implementations throw java.io.IOException on any link failure. */
interface ElmTransport {
    suspend fun open()

    /** Sends [cmd] and returns the raw response up to (and including) the `>` prompt. */
    suspend fun command(cmd: String, timeoutMs: Long = 3000): String
    fun close()
}
