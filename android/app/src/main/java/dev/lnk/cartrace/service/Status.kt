package dev.lnk.cartrace.service

import dev.lnk.cartrace.gps.GpsFix
import dev.lnk.cartrace.obd.ObdState
import dev.lnk.cartrace.ui.Formatters
import dev.lnk.cartrace.upload.UploadOutcome
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update

/** Process-wide observable state, written by the service and read by the UI. */
object Status {
    private const val MAX_ERRORS = 20

    private val _serviceRunning = MutableStateFlow(false)
    private val _obd = MutableStateFlow<ObdState>(ObdState.Connecting)
    private val _lastFix = MutableStateFlow<GpsFix?>(null)
    private val _queueSize = MutableStateFlow(0)
    private val _lastUpload = MutableStateFlow<Pair<Long, UploadOutcome>?>(null)
    private val _dropped = MutableStateFlow(0)
    private val _errors = MutableStateFlow<List<String>>(emptyList())

    val serviceRunning: StateFlow<Boolean> = _serviceRunning.asStateFlow()
    val obd: StateFlow<ObdState> = _obd.asStateFlow()
    val lastFix: StateFlow<GpsFix?> = _lastFix.asStateFlow()
    val queueSize: StateFlow<Int> = _queueSize.asStateFlow()
    val lastUpload: StateFlow<Pair<Long, UploadOutcome>?> = _lastUpload.asStateFlow()
    val dropped: StateFlow<Int> = _dropped.asStateFlow()
    val errors: StateFlow<List<String>> = _errors.asStateFlow()

    fun setServiceRunning(v: Boolean) { _serviceRunning.value = v }
    fun setObd(v: ObdState) { _obd.value = v }
    fun setLastFix(v: GpsFix) { _lastFix.value = v }
    fun setQueueSize(v: Int) { _queueSize.value = v }
    fun setLastUpload(atMs: Long, outcome: UploadOutcome) { _lastUpload.value = atMs to outcome }
    /** Stores the latest upload outcome and notes data loss (discarded batch, rejected records) in the errors. */
    fun recordUpload(atMs: Long, outcome: UploadOutcome) {
        setLastUpload(atMs, outcome)
        Formatters.uploadError(outcome)?.let { addError(it) }
    }

    fun setDropped(v: Int) { _dropped.value = v }

    fun addError(message: String) {
        _errors.update { (it + message).takeLast(MAX_ERRORS) }
    }

    fun reset() {
        _serviceRunning.value = false
        _obd.value = ObdState.Connecting
        _lastFix.value = null
        _queueSize.value = 0
        _lastUpload.value = null
        _dropped.value = 0
        _errors.value = emptyList()
    }
}
