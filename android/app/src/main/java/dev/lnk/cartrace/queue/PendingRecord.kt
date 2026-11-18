package dev.lnk.cartrace.queue

import androidx.room.Entity
import androidx.room.PrimaryKey

/** A record waiting to be uploaded. [json] is the record serialized with ts = 0. */
@Entity(tableName = "pending")
data class PendingRecord(
    @PrimaryKey(autoGenerate = true) val rowId: Long = 0,
    val id: String,
    val bootCount: Int,
    val elapsedMs: Long,
    val wallMs: Long,
    val json: String,
)

/** GPS-derived offset (utc - elapsed) for a boot. */
@Entity(tableName = "boot_offsets")
data class BootOffset(
    @PrimaryKey val bootCount: Int,
    val offsetMs: Long,
)
