package dev.lnk.cartrace.diag

import android.content.Context
import dev.lnk.cartrace.contract.MAX_DIAG_DETAIL
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.jsonArray

interface PendingDiagStore {
    fun add(code: String, text: String)
    fun drain(): List<Pair<String, String>>
}

private const val MAX_PENDING = 20

/** Bounded, corruption-tolerant store over a raw string slot. */
class JsonPendingDiagStore(
    private val read: () -> String?,
    private val write: (String?) -> Unit,
) : PendingDiagStore {

    @Synchronized
    override fun add(code: String, text: String) {
        try {
            val items = load().toMutableList()
            items.add(code.take(MAX_DIAG_DETAIL) to text.take(MAX_DIAG_DETAIL))
            val kept = items.takeLast(MAX_PENDING)
            write(encode(kept))
        } catch (_: Exception) {
            try { write(null) } catch (_: Exception) {}
        }
    }

    @Synchronized
    override fun drain(): List<Pair<String, String>> {
        val items = try { load() } catch (_: Exception) { emptyList() }
        try { write(null) } catch (_: Exception) {}
        return items
    }

    private fun load(): List<Pair<String, String>> {
        val raw = read() ?: return emptyList()
        return try {
            Json.parseToJsonElement(raw).jsonArray.mapNotNull { el ->
                val pair = el.jsonArray
                val c = (pair[0] as? JsonPrimitive)?.contentOrNull
                val t = (pair[1] as? JsonPrimitive)?.contentOrNull
                if (c != null && t != null) c to t else null
            }
        } catch (_: Exception) {
            emptyList()
        }
    }

    private fun encode(items: List<Pair<String, String>>): String =
        JsonArray(items.map { JsonArray(listOf(JsonPrimitive(it.first), JsonPrimitive(it.second))) }).toString()
}

class PrefsPendingDiagStore(context: Context) : PendingDiagStore {
    private val prefs = context.getSharedPreferences("pending_diag", Context.MODE_PRIVATE)
    private val delegate = JsonPendingDiagStore(
        read = { prefs.getString(KEY, null) },
        write = { v ->
            val e = prefs.edit()
            if (v == null) e.remove(KEY) else e.putString(KEY, v)
            e.commit()
        },
    )

    override fun add(code: String, text: String) = delegate.add(code, text)
    override fun drain(): List<Pair<String, String>> = delegate.drain()

    private companion object {
        const val KEY = "items"
    }
}
