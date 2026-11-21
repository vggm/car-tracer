@file:Suppress("PropertyName")

package dev.lnk.cartrace.contract

import kotlinx.serialization.KSerializer
import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import kotlinx.serialization.builtins.ListSerializer
import kotlinx.serialization.descriptors.SerialDescriptor
import kotlinx.serialization.encoding.Decoder
import kotlinx.serialization.encoding.Encoder
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonDecoder

/** Ingest contract v1 (docs/contract/ingest-v1.md). Property names match the JSON. */
@Serializable
sealed interface Record {
    val id: String
    val session_id: String
    val seq: Long
    val ts: Long
}

@Serializable
@SerialName("gps")
data class GpsRecord(
    override val id: String,
    override val session_id: String,
    override val seq: Long,
    override val ts: Long,
    val lat: Double,
    val lon: Double,
    val acc_m: Double,
    val speed_mps: Double? = null,
    val bearing: Double? = null,
    val alt_m: Double? = null,
) : Record

@Serializable
@SerialName("obd")
data class ObdRecord(
    override val id: String,
    override val session_id: String,
    override val seq: Long,
    override val ts: Long,
    val values: Map<String, Double>,
) : Record

@Serializable
@SerialName("dtc")
data class DtcRecord(
    override val id: String,
    override val session_id: String,
    override val seq: Long,
    override val ts: Long,
    val active: List<String>,
    val pending: List<String>,
) : Record

@Serializable
@SerialName("event")
data class EventRecord(
    override val id: String,
    override val session_id: String,
    override val seq: Long,
    override val ts: Long,
    val event: String,
    val detail: String? = null,
) : Record

@Serializable
data class Batch(
    val device_id: String,
    val app_version: String,
    val records: List<Record>,
)

@Serializable
data class Rejected(val index: Int, val id: String? = null, val error: String)

@Serializable
data class IngestResponse(
    val accepted: Int,
    val duplicates: Int,
    val rejected: List<Rejected> = emptyList(),
    @Serializable(with = LenientCommands::class)
    val commands: List<Command> = emptyList(),
)

/** A server request riding on the ingest 200 response; unknown [type]s are ignored by the app. */
@Serializable
data class Command(val type: String, val id: String = "")

/** Decodes each command on its own: a malformed one is skipped instead of failing the whole response. */
object LenientCommands : KSerializer<List<Command>> {
    private val delegate = ListSerializer(Command.serializer())
    override val descriptor: SerialDescriptor = delegate.descriptor

    override fun deserialize(decoder: Decoder): List<Command> {
        val input = decoder as? JsonDecoder ?: return delegate.deserialize(decoder)
        val array = input.decodeJsonElement() as? JsonArray ?: return emptyList()
        return array.mapNotNull { el ->
            try {
                input.json.decodeFromJsonElement(Command.serializer(), el)
            } catch (e: Exception) {
                null
            }
        }
    }

    override fun serialize(encoder: Encoder, value: List<Command>) = delegate.serialize(encoder, value)
}

object Events {
    const val SESSION_START = "session_start"
    const val RESUMED = "resumed"
    const val OBD_CONNECTED = "obd_connected"
    const val OBD_LOST = "obd_lost"
    const val OBD_ERROR = "obd_error"
    const val OBD_ATTEMPT_FAILED = "obd_attempt_failed"
    const val DTC_SCAN = "dtc_scan"
    const val DTC_SCAN_FAILED = "dtc_scan_failed"
    const val DTC_CLEAR = "dtc_clear"
    const val DTC_CLEAR_FAILED = "dtc_clear_failed"
}

val ContractJson: Json = Json {
    classDiscriminator = "type"
    explicitNulls = false
    encodeDefaults = false
    ignoreUnknownKeys = true
}
