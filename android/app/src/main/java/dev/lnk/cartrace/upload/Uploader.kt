package dev.lnk.cartrace.upload

import dev.lnk.cartrace.contract.Batch
import dev.lnk.cartrace.contract.Command
import dev.lnk.cartrace.contract.ContractJson
import dev.lnk.cartrace.contract.IngestResponse
import dev.lnk.cartrace.queue.ReadyBatch
import dev.lnk.cartrace.queue.RecordQueue
import dev.lnk.cartrace.settings.AppSettings
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.jsonPrimitive
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import java.io.IOException

/** One upload attempt per call; the owning service runs the retry loop (see [UploadPolicy]). */
class Uploader(
    private val queue: RecordQueue,
    private val settings: AppSettings,
    http: OkHttpClient,
    private val appVersion: String,
    private val offsets: suspend () -> Map<Int, Long>,
    private val currentBoot: () -> Int,
    private val onCommands: (List<Command>) -> Unit = {},
) {
    private val http: OkHttpClient = http.newBuilder().followRedirects(false).followSslRedirects(false).build()

    suspend fun uploadOnce(maxRecords: Int = 500): UploadOutcome {
        val url = settings.serverUrl.trim()
        val token = settings.token.trim()
        val deviceId = settings.deviceId
        if (url.isEmpty() || token.isEmpty()) return UploadOutcome.Retry("not configured")
        val ready = queue.nextBatch(maxRecords.coerceIn(1, MAX_RECORDS), offsets(), currentBoot())
        if (ready.records.isEmpty()) return UploadOutcome.Idle
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
                    val r = parse((outcome as HttpResult.Response).body)
                        ?: return UploadOutcome.Retry("unexpected response")
                    queue.remove(ready.rowIds.take(count))
                    val commands = r.commands.filter { it.id.isNotBlank() }
                    if (commands.isNotEmpty()) runCatching { onCommands(commands) }
                    return UploadOutcome.Sent(r.accepted, r.duplicates, r.rejected.size, r.rejected.firstOrNull()?.error?.take(200))
                }
                UploadOutcomeKind.DISCARD -> {
                    // Only our server answers {"error": ...}; any other 400 (a TLS port, a proxy) keeps the rows.
                    val reason = serverError((outcome as HttpResult.Response).body)
                        ?: return UploadOutcome.Retry("http $code")
                    queue.remove(ready.rowIds.take(count))
                    return UploadOutcome.Discarded(code, reason.take(200))
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

    private fun serverError(body: String): String? = try {
        (ContractJson.parseToJsonElement(body) as? JsonObject)?.get("error")?.jsonPrimitive?.takeIf { it.isString }?.content
    } catch (e: Exception) {
        null
    }

    private sealed interface HttpResult {
        data class Response(val code: Int, val body: String) : HttpResult
        data class Failure(val reason: String) : HttpResult
    }

    private suspend fun post(builder: Request.Builder, token: String, body: ByteArray): HttpResult =
        withContext(Dispatchers.IO) {
            val req = try {
                builder
                    .header("Authorization", "Bearer $token")
                    .post(body.toRequestBody(JSON))
                    .build()
            } catch (e: IllegalArgumentException) {
                return@withContext HttpResult.Failure("invalid token")
            }
            try {
                http.newCall(req).execute().use { HttpResult.Response(it.code, it.body.string()) }
            } catch (e: IOException) {
                HttpResult.Failure("io: ${e.javaClass.simpleName}")
            }
        }

    companion object {
        const val MAX_RECORDS = 500
        const val MAX_BODY_BYTES = 262_144
        private val JSON = "application/json".toMediaType()
    }
}
