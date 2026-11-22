package dev.lnk.cartrace.obd

import org.junit.Assert.assertEquals
import org.junit.Test

class InitVariantsTest {
    @Test
    fun rotationIsStableAndCoversAll() {
        for (id in listOf("s1", "abc", "9f1c-77", "")) {
            assertEquals(variantFor(id, 1), variantFor(id, 1))
            assertEquals(InitVariant.entries.toSet(), (1..5).map { variantFor(id, it) }.toSet())
            assertEquals(variantFor(id, 1), variantFor(id, 6))
            val start = InitVariant.entries.indexOf(variantFor(id, 1))
            assertEquals(Math.floorMod(id.hashCode(), 5), start)
            assertEquals(InitVariant.entries[(start + 1) % 5], variantFor(id, 2))
        }
    }

    private fun render(v: InitVariant) = commandsFor(v).map {
        when (it) {
            is Step.Cmd -> it.text
            is Step.Wait -> "wait${it.ms}"
        }
    }

    @Test
    fun sequencesMatchSpec() {
        val common = listOf("ATE0", "ATL0", "ATS0", "ATH0", "ATSP5")
        assertEquals(listOf("ATZ") + common + "ATKW0", render(InitVariant.V1))
        assertEquals(listOf("ATZ", "wait1000") + common + listOf("ATKW0", "ATFI", "wait500"), render(InitVariant.V2))
        assertEquals(listOf("ATWS", "wait1000") + common + listOf("ATKW0", "ATFI", "wait500"), render(InitVariant.V3))
        assertEquals(listOf("ATZ", "wait1000") + common + listOf("ATST FF", "ATKW0", "ATFI", "wait500"), render(InitVariant.V4))
        assertEquals(listOf("ATZ", "wait1000") + common + listOf("ATKW0", "ATFI", "ATSH 81 10 F1", "wait500"), render(InitVariant.V5))
    }
}
