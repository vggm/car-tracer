package dev.lnk.cartrace.obd

import org.junit.Assert.assertEquals
import org.junit.Test
import java.io.ByteArrayInputStream
import java.io.IOException

class ReadUntilPromptTest {
    @Test
    fun stopsAtPromptAndLeavesRest() {
        val input = ByteArrayInputStream("41 0C 1A F8\r\r>NEXT".toByteArray())
        assertEquals("41 0C 1A F8\r\r>", readUntilPrompt(input))
        assertEquals('N'.code, input.read())
    }

    @Test(expected = IOException::class)
    fun eofWithoutPromptThrows() {
        readUntilPrompt(ByteArrayInputStream("NO DA".toByteArray()))
    }
}
