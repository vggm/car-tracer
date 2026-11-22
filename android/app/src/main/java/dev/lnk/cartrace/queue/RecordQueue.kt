package dev.lnk.cartrace.queue

import dev.lnk.cartrace.contract.ContractJson
import dev.lnk.cartrace.contract.DtcRecord
import dev.lnk.cartrace.contract.EventRecord
import dev.lnk.cartrace.contract.GpsRecord
import dev.lnk.cartrace.contract.HealthRecord
import dev.lnk.cartrace.contract.ObdRecord
import dev.lnk.cartrace.contract.Record
import dev.lnk.cartrace.core.Resolution
import dev.lnk.cartrace.core.SessionClock
import dev.lnk.cartrace.core.Stamp
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.serialization.SerializationException

data class ReadyBatch(val rowIds: List<Long>, val records: List<Record>)

private fun Record.withTs(ts: Long): Record = when (this) {
    is GpsRecord -> copy(ts = ts)
    is ObdRecord -> copy(ts = ts)
    is DtcRecord -> copy(ts = ts)
    is EventRecord -> copy(ts = ts)
    is HealthRecord -> copy(ts = ts)
}

/** Durable FIFO queue of records; timestamps are resolved to UTC when handed out. */
class RecordQueue(
    private val dao: QueueDao,
    private val clock: SessionClock,
    private val maxRows: Int = 200_000,
) {
    private val _dropped = MutableStateFlow(0)
    val droppedCount: StateFlow<Int> = _dropped.asStateFlow()

    suspend fun add(record: Record, stamp: Stamp) {
        val json = ContractJson.encodeToString(Record.serializer(), record.withTs(0))
        dao.addCapped(
            PendingRecord(
                id = record.id,
                bootCount = stamp.bootCount,
                elapsedMs = stamp.elapsedMs,
                wallMs = stamp.wallMs,
                json = json,
            ),
            maxRows,
        )
    }

    /** FIFO: drops unresolvable rows of previous boots, stops at the first row that must wait. */
    suspend fun nextBatch(maxRecords: Int, offsets: Map<Int, Long>, currentBoot: Int): ReadyBatch {
        val ids = ArrayList<Long>()
        val records = ArrayList<Record>()
        val toDrop = ArrayList<Long>()
        var after = Long.MIN_VALUE
        var waiting = false
        while (!waiting && ids.size < maxRecords) {
            val page = dao.page(after, maxRecords)
            if (page.isEmpty()) break
            after = page.last().rowId
            for (row in page) {
                if (ids.size >= maxRecords) break
                when (val r = clock.resolve(Stamp(row.bootCount, row.elapsedMs, row.wallMs), offsets, currentBoot)) {
                    is Resolution.Ts -> {
                        val rec = try {
                            ContractJson.decodeFromString(Record.serializer(), row.json).withTs(r.utcMs)
                        } catch (e: SerializationException) {
                            null
                        } catch (e: IllegalArgumentException) {
                            null
                        }
                        if (rec == null) {
                            toDrop += row.rowId
                        } else {
                            ids += row.rowId
                            records += rec
                        }
                    }
                    Resolution.Drop -> toDrop += row.rowId
                    Resolution.Wait -> { waiting = true; break }
                }
            }
        }
        if (toDrop.isNotEmpty()) {
            toDrop.chunked(500).forEach { dao.delete(it) }
            _dropped.update { it + toDrop.size }
        }
        return ReadyBatch(ids, records)
    }

    suspend fun remove(rowIds: List<Long>) {
        rowIds.chunked(500).forEach { dao.delete(it) }
    }

    suspend fun size(): Int = dao.count()
}
