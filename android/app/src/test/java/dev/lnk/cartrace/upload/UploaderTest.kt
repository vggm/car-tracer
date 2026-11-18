package dev.lnk.cartrace.upload

import android.content.Context
import androidx.room.Room
import androidx.test.core.app.ApplicationProvider
import dev.lnk.cartrace.contract.Batch
import dev.lnk.cartrace.contract.ContractJson
import dev.lnk.cartrace.contract.EventRecord
import dev.lnk.cartrace.core.SessionClock
import dev.lnk.cartrace.core.Stamp
import dev.lnk.cartrace.queue.AppDatabase
import dev.lnk.cartrace.queue.RecordQueue
import dev.lnk.cartrace.settings.AppSettings
import kotlinx.coroutines.test.runTest
import okhttp3.OkHttpClient
import okhttp3.mockwebserver.Dispatcher
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import okhttp3.mockwebserver.RecordedRequest
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config

private const val FAKE_A = "fake-a"
private const val FAKE_B = "fake-b"
private const val BAD_CHARS = "ab\u0001c\u00e9"
private const val PADDED = "abc\n"

@RunWith(RobolectricTestRunner::class)
@Config(sdk = [34])
class UploaderTest {
    private val min = 1_700_000_000_000L
    private lateinit var db: AppDatabase
    private lateinit var queue: RecordQueue
    private lateinit var settings: AppSettings
    private lateinit var server: MockWebServer
    private lateinit var uploader: Uploader

    @Before fun setUp() {
        val ctx = ApplicationProvider.getApplicationContext<Context>()
        db = Room.inMemoryDatabaseBuilder(ctx, AppDatabase::class.java).allowMainThreadQueries().build()
        queue = RecordQueue(db.queueDao(), SessionClock(min))
        settings = AppSettings(ctx.getSharedPreferences("test-settings", Context.MODE_PRIVATE))
        server = MockWebServer().also { it.start() }
        settings.serverUrl = server.url("/api/v1/ingest").toString()
        settings.apply { token = FAKE_A }
        uploader = Uploader(queue, settings, OkHttpClient(), "1.0-test", { db.queueDao().offsets().associate { it.bootCount to it.offsetMs } }, { 1 })
    }

    @After fun tearDown() { server.shutdown(); db.close() }

    private suspend fun fill(n: Int) {
        for (i in 1..n) queue.add(EventRecord("id$i", "s", i.toLong(), 0, "e$i"), Stamp(1, i * 1000L, min + i))
    }

    private fun ok() = MockResponse().setResponseCode(200).setBody("""{"accepted":1,"duplicates":0,"rejected":[]}""")

    @Test fun sends200RemovesRows() = runTest {
        fill(3)
        server.enqueue(MockResponse().setResponseCode(200).setBody("""{"accepted":2,"duplicates":1,"rejected":[]}"""))
        assertEquals(UploadOutcome.Sent(2, 1, 0), uploader.uploadOnce())
        assertEquals(0, queue.size())
    }

    @Test fun idleWithoutRequest() = runTest {
        assertEquals(UploadOutcome.Idle, uploader.uploadOnce())
        assertEquals(0, server.requestCount)
    }

    @Test fun notConfiguredRetriesWithoutRequest() = runTest {
        fill(1)
        settings.apply { token = "" }
        assertEquals(UploadOutcome.Retry("not configured"), uploader.uploadOnce())
        assertEquals(0, server.requestCount)
        assertEquals(1, queue.size())
    }

    @Test fun discards400() = runTest {
        fill(2)
        server.enqueue(MockResponse().setResponseCode(400))
        assertEquals(UploadOutcome.Discarded(400), uploader.uploadOnce())
        assertEquals(0, queue.size())
    }

    @Test fun keepsRowsOn401() = runTest {
        fill(2)
        server.enqueue(MockResponse().setResponseCode(401))
        assertEquals(UploadOutcome.Unauthorized, uploader.uploadOnce())
        assertEquals(2, queue.size())
    }

    @Test fun retriesOn5xx() = runTest {
        fill(2)
        server.enqueue(MockResponse().setResponseCode(503))
        assertTrue(uploader.uploadOnce() is UploadOutcome.Retry)
        assertEquals(2, queue.size())
    }

    @Test fun retriesOnNetworkError() = runTest {
        fill(2)
        server.shutdown()
        assertTrue(uploader.uploadOnce() is UploadOutcome.Retry)
        assertEquals(2, queue.size())
    }

    @Test fun nonJson200Retries() = runTest {
        fill(2)
        server.enqueue(MockResponse().setResponseCode(200).setBody("<html>ok</html>"))
        assertEquals(UploadOutcome.Retry("unexpected response"), uploader.uploadOnce())
        server.enqueue(MockResponse().setResponseCode(200).setBody("{}"))
        assertEquals(UploadOutcome.Retry("unexpected response"), uploader.uploadOnce())
        assertEquals(2, queue.size())
    }

    @Test fun unknownCodesAndRedirectsKeepRows() = runTest {
        fill(2)
        server.enqueue(MockResponse().setResponseCode(404))
        assertTrue(uploader.uploadOnce() is UploadOutcome.Retry)
        server.enqueue(MockResponse().setResponseCode(302).setHeader("Location", server.url("/other").toString()))
        assertTrue(uploader.uploadOnce() is UploadOutcome.Retry)
        assertEquals(2, server.requestCount)
        assertEquals(2, queue.size())
    }

    @Test fun notConfiguredDoesNotTouchQueue() = runTest {
        queue.add(EventRecord("old", "s", 1, 0, "e"), Stamp(0, 1000L, 1_000L)) // unresolvable earlier boot
        settings.apply { token = "" }
        assertEquals(UploadOutcome.Retry("not configured"), uploader.uploadOnce())
        assertEquals(0, server.requestCount)
        assertEquals(1, queue.size())
    }

    @Test fun trimsTokenWhitespace() = runTest {
        fill(1)
        settings.apply { token = PADDED }
        server.enqueue(ok())
        assertTrue(uploader.uploadOnce() is UploadOutcome.Sent)
        assertEquals("Bearer abc", server.takeRequest().getHeader("Authorization"))
    }

    @Test fun invalidTokenCharsRetryWithoutCrash() = runTest {
        fill(1)
        settings.apply { token = BAD_CHARS }
        assertEquals(UploadOutcome.Retry("invalid token"), uploader.uploadOnce())
        assertEquals(0, server.requestCount)
        assertEquals(1, queue.size())
    }

    @Test fun capsMaxRecordsAt500() = runTest {
        fill(520)
        var n = 0
        server.dispatcher = object : Dispatcher() {
            override fun dispatch(request: RecordedRequest): MockResponse {
                n = ContractJson.decodeFromString(Batch.serializer(), request.body.readUtf8()).records.size
                return ok()
            }
        }
        uploader.uploadOnce(10_000)
        assertEquals(500, n)
        assertEquals(20, queue.size())
    }

    @Test fun `408And429Retry`() = runTest {
        fill(2)
        server.enqueue(MockResponse().setResponseCode(408))
        assertTrue(uploader.uploadOnce() is UploadOutcome.Retry)
        server.enqueue(MockResponse().setResponseCode(429))
        assertTrue(uploader.uploadOnce() is UploadOutcome.Retry)
        assertEquals(2, queue.size())
    }

    @Test fun splitsOn413() = runTest {
        fill(5)
        val sizes = mutableListOf<Int>()
        server.dispatcher = object : Dispatcher() {
            override fun dispatch(request: RecordedRequest): MockResponse {
                val n = ContractJson.decodeFromString(Batch.serializer(), request.body.readUtf8()).records.size
                sizes += n
                return if (n > 2) MockResponse().setResponseCode(413) else ok()
            }
        }
        assertTrue(uploader.uploadOnce() is UploadOutcome.Sent)
        assertEquals(listOf(5, 2), sizes)
        assertEquals(3, queue.size())
        // FIFO preserved: next call starts with the 3rd record (3 -> 413 -> 1)
        assertTrue(uploader.uploadOnce() is UploadOutcome.Sent)
        assertEquals(2, queue.size())
        assertEquals("id4", queue.nextBatch(1, emptyMap(), 1).records.single().id)
    }

    @Test fun singleRecord413IsDiscarded() = runTest {
        fill(1)
        server.enqueue(MockResponse().setResponseCode(413))
        assertEquals(UploadOutcome.Discarded(413), uploader.uploadOnce())
        assertEquals(0, queue.size())
    }

    @Test fun splitsBeforeSendingWhenTooBig() = runTest {
        val big = "x".repeat(60_000)
        for (i in 1..8) queue.add(EventRecord("id$i", "s", i.toLong(), 0, "e", big), Stamp(1, i * 1000L, min + i))
        val sizes = mutableListOf<Int>()
        server.dispatcher = object : Dispatcher() {
            override fun dispatch(request: RecordedRequest): MockResponse {
                sizes += ContractJson.decodeFromString(Batch.serializer(), request.body.readUtf8()).records.size
                return ok()
            }
        }
        assertTrue(uploader.uploadOnce() is UploadOutcome.Sent)
        assertEquals(listOf(4), sizes) // 8*60k > 256k, 4*60k = 240k fits
        assertEquals(4, queue.size())
    }

    @Test fun usesUpdatedSettingsWithoutRestart() = runTest {
        fill(1)
        val second = MockWebServer().also { it.start() }
        try {
            settings.serverUrl = second.url("/api/v1/ingest").toString()
            settings.apply { token = FAKE_B }
            second.enqueue(ok())
            assertTrue(uploader.uploadOnce() is UploadOutcome.Sent)
            assertEquals(0, server.requestCount)
            assertEquals("Bearer $FAKE_B", second.takeRequest().getHeader("Authorization"))
        } finally { second.shutdown() }
    }

    @Test fun sendsBearerAndJson() = runTest {
        fill(1)
        settings.deviceId = "dev-x"
        server.enqueue(ok())
        uploader.uploadOnce()
        val req = server.takeRequest()
        assertEquals("POST", req.method)
        assertEquals("Bearer $FAKE_A", req.getHeader("Authorization"))
        assertTrue(req.getHeader("Content-Type")!!.startsWith("application/json"))
        val batch = ContractJson.decodeFromString(Batch.serializer(), req.body.readUtf8())
        assertEquals("dev-x", batch.device_id)
        assertEquals("1.0-test", batch.app_version)
        assertEquals(min + 1, batch.records.single().ts)
    }
}
