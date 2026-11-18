package dev.lnk.cartrace.queue

import android.content.Context
import androidx.room.Room
import androidx.test.core.app.ApplicationProvider
import dev.lnk.cartrace.contract.ContractJson
import dev.lnk.cartrace.contract.EventRecord
import dev.lnk.cartrace.contract.Record
import dev.lnk.cartrace.contract.ObdRecord
import dev.lnk.cartrace.core.SessionClock
import dev.lnk.cartrace.core.Stamp
import kotlinx.coroutines.test.runTest
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config

@RunWith(RobolectricTestRunner::class)
@Config(sdk = [34])
class RecordQueueTest {
    private val min = 1_700_000_000_000L
    private lateinit var db: AppDatabase

    @Before fun setUp() {
        val ctx = ApplicationProvider.getApplicationContext<Context>()
        db = Room.inMemoryDatabaseBuilder(ctx, AppDatabase::class.java).allowMainThreadQueries().build()
    }

    @After fun tearDown() { db.close() }

    private fun queue(maxRows: Int = 200_000) = RecordQueue(db.queueDao(), SessionClock(min), maxRows)

    private fun ev(n: Int) = EventRecord("id$n", "s", n.toLong(), 0, "e$n")
    private fun good(n: Int) = Stamp(1, n * 1000L, min + n)
    private fun bad(boot: Int, n: Int) = Stamp(boot, n * 1000L, 1_000L)

    @Test fun fifoOrderAndTsInjection() = runTest {
        val q = queue()
        q.add(ev(1), good(1))
        q.add(ObdRecord("id2", "s", 2, 0, mapOf("rpm" to 800.0)), good(2))
        q.add(ev(3), good(3))
        val b = q.nextBatch(10, emptyMap(), 1)
        assertEquals(3, b.rowIds.size)
        assertEquals(b.rowIds.sorted(), b.rowIds)
        assertEquals(listOf("id1", "id2", "id3"), b.records.map { it.id })
        assertEquals(listOf(min + 1, min + 2, min + 3), b.records.map { it.ts })
        assertEquals(ev(1).copy(ts = min + 1), b.records[0])
        assertEquals(ObdRecord("id2", "s", 2, min + 2, mapOf("rpm" to 800.0)), b.records[1])
        assertEquals(2, q.nextBatch(2, emptyMap(), 1).records.size)
        q.remove(b.rowIds)
        assertEquals(0, q.size())
    }

    @Test fun capDeletesOldest() = runTest {
        val q = queue(maxRows = 10)
        for (i in 1..12) q.add(ev(i), good(i))
        assertEquals(10, q.size())
        val b = q.nextBatch(100, emptyMap(), 1)
        assertEquals((3..12).map { "id$it" }, b.records.map { it.id })
    }

    @Test fun previousBootWithoutTimeIsDroppedAndCounted() = runTest {
        val q = queue()
        q.add(ev(1), bad(1, 1))
        q.add(ev(2), bad(1, 2))
        q.add(ev(3), good(3))
        val b = q.nextBatch(10, emptyMap(), 2)
        assertEquals(listOf("id3"), b.records.map { it.id })
        assertEquals(2, q.droppedCount.value)
        assertEquals(1, q.size())
    }

    @Test fun stopsAtFirstWaitInCurrentBoot() = runTest {
        val q = queue()
        q.add(ev(1), good(1))
        q.add(ev(2), bad(2, 2))
        q.add(ev(3), good(3))
        val b = q.nextBatch(10, emptyMap(), 2)
        assertEquals(listOf("id1"), b.records.map { it.id })
        assertEquals(3, q.size())
        // once the boot gets an offset, the waiting row resolves
        val b2 = q.nextBatch(10, mapOf(2 to 5_000L), 2)
        assertEquals(listOf("id1", "id2", "id3"), b2.records.map { it.id })
        assertEquals(7_000L, b2.records[1].ts)
    }

    @Test fun offsetsKeepFirstValue() = runTest {
        val dao = db.queueDao()
        dao.saveOffset(BootOffset(1, 100))
        dao.saveOffset(BootOffset(1, 999))
        assertEquals(listOf(BootOffset(1, 100)), dao.offsets())
    }

    @Test fun previousBootDropThenCurrentBootWaitStopsAtWait() = runTest {
        val q = queue()
        q.add(ev(1), bad(1, 1))
        q.add(ev(2), bad(2, 2))
        q.add(ev(3), good(3))
        val b = q.nextBatch(10, emptyMap(), 2)
        assertEquals(emptyList<String>(), b.records.map { it.id })
        assertEquals(1, q.droppedCount.value)
        assertEquals(2, q.size())
    }

    @Test fun scanCrossesSeveralPages() = runTest {
        val q = queue()
        for (i in 1..7) q.add(ev(i), bad(1, i))
        q.add(ev(8), good(8))
        q.add(ev(9), good(9))
        val b = q.nextBatch(2, emptyMap(), 2)
        assertEquals(listOf("id8", "id9"), b.records.map { it.id })
        assertEquals(7, q.droppedCount.value)
        assertEquals(2, q.size())
    }

    @Test fun headDeletedBetweenPagesDoesNotSkipRows() = runTest {
        val real = db.queueDao()
        fun row(n: Int, boot: Int, wall: Long) = PendingRecord(id = "id$n", bootCount = boot, elapsedMs = 0, wallMs = wall,
            json = ContractJson.encodeToString(Record.serializer(), ev(n)))
        real.insert(row(1, 1, 1))        // previous boot, no time: Drop
        real.insert(row(2, 1, 1))        // Drop
        real.insert(row(3, 2, min + 3))  // ok
        real.insert(row(4, 2, min + 4))  // ok
        real.insert(row(5, 2, 1))        // Wait
        real.insert(row(6, 2, min + 6))  // resolvable but behind the Wait
        var calls = 0
        val spy = object : QueueDao() {
            override suspend fun insert(row: PendingRecord) = real.insert(row)
            override suspend fun count() = real.count()
            override suspend fun page(afterRowId: Long, limit: Int): List<PendingRecord> {
                val r = real.page(afterRowId, limit)
                if (++calls == 1) real.deleteOldest(2) // concurrent cap eviction between pages
                return r
            }
            override suspend fun delete(rowIds: List<Long>) = real.delete(rowIds)
            override suspend fun deleteOldest(n: Int) = real.deleteOldest(n)
            override suspend fun saveOffset(offset: BootOffset) = real.saveOffset(offset)
            override suspend fun offsets() = real.offsets()
        }
        val b = RecordQueue(spy, SessionClock(min), 200_000).nextBatch(2, emptyMap(), 2)
        assertEquals(listOf("id3", "id4"), b.records.map { it.id })
        val b2 = RecordQueue(spy, SessionClock(min), 200_000).nextBatch(10, emptyMap(), 2)
        assertEquals(listOf("id3", "id4"), b2.records.map { it.id }) // stops at the Wait, id6 not sent
    }

    @Test fun undecodableRowIsDroppedAndCounted() = runTest {
        val dao = db.queueDao()
        dao.insert(PendingRecord(id = "bad", bootCount = 1, elapsedMs = 0, wallMs = min, json = "{not json"))
        val q = queue()
        q.add(ev(2), good(2))
        val b = q.nextBatch(10, emptyMap(), 1)
        assertEquals(listOf("id2"), b.records.map { it.id })
        assertEquals(1, q.droppedCount.value)
        assertEquals(1, q.size())
    }
}
