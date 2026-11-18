package dev.lnk.cartrace.queue

import androidx.room.Dao
import androidx.room.Insert
import androidx.room.OnConflictStrategy
import androidx.room.Query
import androidx.room.Transaction

@Dao
abstract class QueueDao {
    @Insert
    abstract suspend fun insert(row: PendingRecord): Long

    @Query("SELECT COUNT(*) FROM pending")
    abstract suspend fun count(): Int

    @Query("SELECT * FROM pending WHERE rowId > :afterRowId ORDER BY rowId ASC LIMIT :limit")
    abstract suspend fun page(afterRowId: Long, limit: Int): List<PendingRecord>

    @Query("DELETE FROM pending WHERE rowId IN (:rowIds)")
    abstract suspend fun delete(rowIds: List<Long>)

    @Query("DELETE FROM pending WHERE rowId IN (SELECT rowId FROM pending ORDER BY rowId ASC LIMIT :n)")
    abstract suspend fun deleteOldest(n: Int)

    @Insert(onConflict = OnConflictStrategy.IGNORE)
    abstract suspend fun saveOffset(offset: BootOffset)

    @Query("SELECT * FROM boot_offsets")
    abstract suspend fun offsets(): List<BootOffset>

    /** Insert and enforce the cap atomically. */
    @Transaction
    open suspend fun addCapped(row: PendingRecord, maxRows: Int) {
        insert(row)
        val surplus = count() - maxRows
        if (surplus > 0) deleteOldest(surplus)
    }
}
