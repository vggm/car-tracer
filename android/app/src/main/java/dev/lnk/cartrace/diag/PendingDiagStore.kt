package dev.lnk.cartrace.diag

import android.content.Context
import org.json.JSONArray
import org.json.JSONObject

interface PendingDiagStore {
    fun add(code: String, text: String)
    fun drain(): List<Pair<String, String>>
}

class PrefsPendingDiagStore(context: Context) : PendingDiagStore {
    private val prefs = context.getSharedPreferences("pending_diag", Context.MODE_PRIVATE)

    @Synchronized
    override fun add(code: String, text: String) {
        val arr = JSONArray(prefs.getString(KEY, "[]"))
        arr.put(JSONObject().put("c", code).put("t", text))
        prefs.edit().putString(KEY, arr.toString()).commit()
    }

    @Synchronized
    override fun drain(): List<Pair<String, String>> {
        val arr = JSONArray(prefs.getString(KEY, "[]"))
        val out = (0 until arr.length()).map {
            val o = arr.getJSONObject(it)
            o.getString("c") to o.getString("t")
        }
        prefs.edit().remove(KEY).commit()
        return out
    }

    private companion object {
        const val KEY = "items"
    }
}
