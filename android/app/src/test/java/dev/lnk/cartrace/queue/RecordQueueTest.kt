package dev.lnk.cartrace.queue

import android.content.Context
import androidx.room.Room
import androidx.test.core.app.ApplicationProvider
import dev.lnk.cartrace.contract.EventRecord
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
}
