package dev.lnk.cartrace.obd

/** KWP (protocol 5) init sequences tried in rotation to find out what a cold ECU accepts. */
enum class InitVariant { V1, V2, V3, V4, V5 }

sealed interface Step {
    data class Cmd(val text: String, val timeoutMs: Long = 3_000L) : Step
    data class Wait(val ms: Long) : Step
}

/** Attempt [attempt] (1-based) of a session uses `(start + attempt - 1) mod 5`, start derived from the session id. */
fun variantFor(sessionId: String, attempt: Int): InitVariant {
    val start = Math.floorMod(sessionId.hashCode(), InitVariant.entries.size)
    return InitVariant.entries[Math.floorMod(start + attempt - 1, InitVariant.entries.size)]
}

private const val RESET_TIMEOUT = 10_000L

/** Steps before the 0100 PID loop. */
fun commandsFor(v: InitVariant): List<Step> {
    fun c(t: String, timeout: Long = 3_000L) = Step.Cmd(t, timeout)
    if (v == InitVariant.V1) {
        return listOf(c("ATZ", RESET_TIMEOUT), c("ATE0"), c("ATL0"), c("ATS0"), c("ATH0"), c("ATSP5"), c("ATKW0"))
    }
    val reset = if (v == InitVariant.V3) c("ATWS", RESET_TIMEOUT) else c("ATZ", RESET_TIMEOUT)
    return buildList {
        add(reset)
        add(Step.Wait(1_000))
        add(c("ATE0")); add(c("ATL0")); add(c("ATS0")); add(c("ATH0")); add(c("ATSP5"))
        if (v == InitVariant.V4) add(c("ATST FF"))
        add(c("ATKW0"))
        add(c("ATFI", RESET_TIMEOUT)) // fast init may take several seconds
        if (v == InitVariant.V5) add(c("ATSH 81 10 F1"))
        add(Step.Wait(500))
    }
}
