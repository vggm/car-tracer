package dev.lnk.cartrace.service

import android.content.Context
import androidx.room.Room
import dev.lnk.cartrace.core.AndroidClocks
import dev.lnk.cartrace.core.Clocks
import dev.lnk.cartrace.core.SessionClock
import dev.lnk.cartrace.queue.AppDatabase
import dev.lnk.cartrace.queue.RecordQueue
import dev.lnk.cartrace.settings.AppSettings
import okhttp3.OkHttpClient

/** Application-level singletons: one database, one queue, one settings store. */
class AppGraph private constructor(context: Context) {
    private val app = context.applicationContext

    val settings = AppSettings(app.getSharedPreferences(PREFS, Context.MODE_PRIVATE))
    val clocks: Clocks = AndroidClocks(app)
    val sessionClock = SessionClock()
    val database: AppDatabase = Room.databaseBuilder(app, AppDatabase::class.java, "car-trace.db").build()
    val dao = database.queueDao()
    val queue = RecordQueue(dao, sessionClock)
    val http: OkHttpClient = OkHttpClient()

    companion object {
        const val PREFS = "car-trace-settings"

        @Volatile private var instance: AppGraph? = null

        fun get(context: Context): AppGraph =
            instance ?: synchronized(this) { instance ?: AppGraph(context).also { instance = it } }
    }
}
