package dev.lnk.cartrace.upload

import dev.lnk.cartrace.contract.Batch
import dev.lnk.cartrace.contract.ContractJson
import dev.lnk.cartrace.contract.IngestResponse
import dev.lnk.cartrace.queue.ReadyBatch
import dev.lnk.cartrace.queue.RecordQueue
import dev.lnk.cartrace.settings.AppSettings
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import java.io.IOException

/** One upload attempt per call; the owning service runs the retry loop (see [UploadPolicy]). */
class Uploader(
    private val queue: RecordQueue,
    private val settings: AppSettings,
    private val http: OkHttpClient,
    private val appVersion: String,
    private val offsets: suspend () -> Map<Int, Long>,
    private val currentBoot: () -> Int,
) {
    suspend fun uploadOnce(maxRecords: Int = 500): UploadOutcome {
        val url = settings.serverUrl.trim()
        val token = settings.token
        val deviceId = settings.deviceId
        val ready = queue.nextBatch(maxRecords, offsets(), currentBoot())
        if (ready.records.isEmpty()) return UploadOutcome.Idle
        if (url.isEmpty() || token.isEmpty()) return UploadOutcome.Retry("not configured")
        val request = try {
            Request.Builder().url(url)
        } catch (e: IllegalArgumentException) {
            return UploadOutcome.Retry("invalid server url")
        }
        return send(ready, request, token, deviceId)
    }

    private suspend fun send(ready: ReadyBatch, builder: Request.Builder, token: String, deviceId: String): UploadOutcome {
        var count = ready.records.size
        var body = encode(ready, count, deviceId)
        while (count > 1 && body.size > MAX_BODY_BYTES) {
            count = (count + 1) / 2
            body = encode(ready, count, deviceId)
        }
        while (true) {
            val outcome = post(builder, token, body)
            val code = (outcome as? HttpResult.Response)?.code
            if (outcome is HttpResult.Failure) return UploadOutcome.Retry(outcome.reason)
            when (UploadPolicy.classify(code!!)) {
                UploadOutcomeKind.TOO_LARGE -> {
                    if (count == 1) {
                        queue.remove(ready.rowIds.take(1))
                        return UploadOutcome.Discarded(code)
                    }
                    count /= 2
                    body = encode(ready, count, deviceId)
                }
                UploadOutcomeKind.SENT -> {
                    queue.remove(ready.rowIds.take(count))
                    val r = parse((outcome as HttpResult.Response).body)
                    return UploadOutcome.Sent(r?.accepted ?: 0, r?.duplicates ?: 0, r?.rejected?.size ?: 0)
                }
                UploadOutcomeKind.DISCARD -> {
                    queue.remove(ready.rowIds.take(count))
                    return UploadOutcome.Discarded(code)
                }
                UploadOutcomeKind.UNAUTHORIZED -> return UploadOutcome.Unauthorized
                UploadOutcomeKind.RETRY -> return UploadOutcome.Retry("http $code")
            }
        }
    }

    private fun encode(ready: ReadyBatch, count: Int, deviceId: String): ByteArray =
        ContractJson.encodeToString(Batch.serializer(), Batch(deviceId, appVersion, ready.records.take(count)))
            .toByteArray(Charsets.UTF_8)

    private fun parse(body: String): IngestResponse? = try {
        ContractJson.decodeFromString(IngestResponse.serializer(), body)
    } catch (e: Exception) {
        null
    }

    private sealed interface HttpResult {
        data class Response(val code: Int, val body: String) : HttpResult
        data class Failure(val reason: String) : HttpResult
    }

    private suspend fun post(builder: Request.Builder, token: String, body: ByteArray): HttpResult =
        withContext(Dispatchers.IO) {
            val req = builder
                .header("Authorization", "Bearer $token")
                .post(body.toRequestBody(JSON))
                .build()
            try {
                http.newCall(req).execute().use { HttpResult.Response(it.code, it.body.string()) }
            } catch (e: IOException) {
                HttpResult.Failure("io: ${e.javaClass.simpleName}")
            }
        }

    companion object {
        const val MAX_BODY_BYTES = 262_144
        private val JSON = "application/json".toMediaType()
    }
}
