package dev.lnk.cartrace.queue

import androidx.room.Database
import androidx.room.RoomDatabase

@Database(entities = [PendingRecord::class, BootOffset::class], version = 1, exportSchema = true)
abstract class AppDatabase : RoomDatabase() {
    abstract fun queueDao(): QueueDao
}
