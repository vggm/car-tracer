package dev.lnk.cartrace.contract

import java.io.File
import kotlinx.serialization.encodeToString
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.doubleOrNull
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class RecordsTest {

    /** Normalizes numbers to Double so that 88 and 88.0 compare equal. */
    private fun normalize(e: JsonElement): JsonElement = when (e) {
        is JsonObject -> JsonObject(e.mapValues { normalize(it.value) })
        is JsonArray -> JsonArray(e.map { normalize(it) })
        is JsonNull -> e
        is JsonPrimitive ->
            if (!e.isString) e.doubleOrNull?.let { JsonPrimitive(it) } ?: e else e
    }

    @Test
    fun examplesRoundTrip() {
        val file = File("../../docs/contract/examples/valid-mixed.json")
        val request = Json.parseToJsonElement(file.readText()).jsonObject.getValue("request")
        val batch = ContractJson.decodeFromString<Batch>(request.toString())
        assertEquals(6, batch.records.size)
        val encoded = ContractJson.parseToJsonElement(ContractJson.encodeToString(batch))
        assertEquals(normalize(request), normalize(encoded))
    }

    @Test
    fun optionalGpsFieldsOmittedWhenNull() {
        val rec = GpsRecord(
            id = "i", session_id = "s", seq = 1, ts = 2,
            lat = 1.0, lon = 2.0, acc_m = 3.0,
        )
        val obj = ContractJson.parseToJsonElement(ContractJson.encodeToString<Record>(rec)).jsonObject
        assertEquals("gps", (obj.getValue("type") as JsonPrimitive).content)
        for (k in listOf("speed_mps", "bearing", "alt_m")) assertFalse(k, obj.containsKey(k))
        val ev = ContractJson.parseToJsonElement(
            ContractJson.encodeToString<Record>(EventRecord("i", "s", 0, 1, Events.SESSION_START, null))
        ).jsonObject
        assertFalse(ev.containsKey("detail"))
    }

    @Test
    fun responseDecodesRejected() {
        val r = ContractJson.decodeFromString<IngestResponse>(
            """{"accepted":3,"duplicates":1,"rejected":[{"index":2,"id":"abc","error":"bad ts"}]}"""
        )
        assertEquals(3, r.accepted)
        assertEquals(1, r.duplicates)
        assertEquals(1, r.rejected.size)
        assertEquals(2, r.rejected[0].index)
        assertEquals("abc", r.rejected[0].id)
        assertTrue(r.rejected[0].error.isNotEmpty())
    }
}
