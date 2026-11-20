package dev.lnk.cartrace.service

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.Service
import android.content.Intent
import android.content.pm.ServiceInfo
import android.os.IBinder
import android.util.Log
import dev.lnk.cartrace.BuildConfig
import dev.lnk.cartrace.contract.EventRecord
import dev.lnk.cartrace.contract.Events
import dev.lnk.cartrace.contract.GpsRecord
import dev.lnk.cartrace.core.OffsetRecorder
import dev.lnk.cartrace.core.Session
import dev.lnk.cartrace.core.SleepDetector
import dev.lnk.cartrace.core.Stamp
import dev.lnk.cartrace.core.stamp
import dev.lnk.cartrace.gps.AndroidGpsSource
import dev.lnk.cartrace.gps.GpsFix
import dev.lnk.cartrace.gps.GpsSource
import dev.lnk.cartrace.obd.BluetoothElmTransport
import dev.lnk.cartrace.obd.ElmLog
import dev.lnk.cartrace.obd.LoggingElmTransport
import dev.lnk.cartrace.obd.ObdSource
import dev.lnk.cartrace.obd.ObdState
import dev.lnk.cartrace.settings.SettingsSnapshot
import dev.lnk.cartrace.sim.FakeElmTransport
import dev.lnk.cartrace.sim.FakeGpsSource
import dev.lnk.cartrace.upload.UploadOutcome
import dev.lnk.cartrace.upload.Uploader
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.CoroutineExceptionHandler
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.cancelAndJoin
import kotlinx.coroutines.isActive
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import android.Manifest
import android.content.pm.PackageManager
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.coroutineScope
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.distinctUntilChanged
import kotlinx.coroutines.flow.drop
import kotlinx.coroutines.flow.map
import kotlinx.coroutines.launch
import java.util.UUID
import java.util.concurrent.atomic.AtomicReference

class TelemetryService : Service() {
    private var scope: CoroutineScope? = null
    private lateinit var graph: AppGraph
    private lateinit var supervisor: Supervisor
    private val session = AtomicReference(Session())
    private val sleepDetector by lazy { SleepDetector(graph.clocks, 60_000) }
    private var gps: GpsSource? = null
    private var obdJob: Job? = null
    private var started = false
    private val gpsLock = Any()
    private val obdMutex = Mutex()
    private var uploadLoop: UploadLoop? = null

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onCreate() {
        super.onCreate()
        graph = AppGraph.get(this)
        Status.reset()
        val bootCount = graph.clocks.bootCount()
        Status.setBootCount(bootCount)
        Log.i(TAG, "BOOT_COUNT=$bootCount (must increase between ignition cycles)")
        createChannel()
        if (!enterForeground()) {
            stopSelf()
            return
        }
        val handler = CoroutineExceptionHandler { _, e ->
            Log.e(TAG, "uncaught exception in service scope", e)
            Status.addError("uncaught: ${e.javaClass.simpleName}: ${e.message ?: ""}".trim())
        }
        val s = CoroutineScope(SupervisorJob() + Dispatchers.Default + handler)
        scope = s
        supervisor = Supervisor(s)
        started = true
        Status.setServiceRunning(true)

        s.launch {
            // session_start goes in before any source can take a seq number
            safely("session_start") { emitEvent(session.get(), Events.SESSION_START, null) }
            startChildren()
        }
    }

    private fun startChildren() {
        val loop = buildUploadLoop()
        uploadLoop = loop
        supervisor.launch("sources") {
            graph.settings.changes
                .map { Triple(it.simulated, it.adapterAddress, it.obdProtocol) }
                .distinctUntilChanged()
                .collect { restartSources(graph.settings.snapshot()) }
        }
        supervisor.launch("uploader") { loop.run() }
        supervisor.launch("upload-config") {
            graph.settings.changes
                .map { it.serverUrl to it.token }
                .distinctUntilChanged()
                .drop(1)
                .collect { loop.resetBackoff() }
        }
        supervisor.launch("sleep") {
            while (true) {
                delay(SLEEP_TICK_MS)
                if (sleepDetector.tick()) onResumed()
            }
        }
        supervisor.launch("status") {
            while (true) {
                Status.setQueueSize(graph.queue.size())
                Status.setDropped(graph.queue.droppedCount.value)
                notify(Status.queueSize.value)
                delay(NOTIFY_EVERY_MS)
            }
        }
    }

    /** Enters foreground with the types currently allowed; false if the service must stop. */
    private fun enterForeground(): Boolean {
        val btGranted = checkSelfPermission(Manifest.permission.BLUETOOTH_CONNECT) == PackageManager.PERMISSION_GRANTED
        val full = foregroundTypes(btGranted)
        val locationOnly = foregroundTypes(false)
        val attempts = if (full == locationOnly) listOf(full) else listOf(full, locationOnly)
        for (types in attempts) {
            try {
                startForeground(NOTIFICATION_ID, buildNotification(0), types)
                return true
            } catch (e: Exception) {
                Log.e(TAG, "startForeground failed (types=$types)", e)
                Status.addError("startForeground: ${e.javaClass.simpleName}: ${e.message ?: ""}".trim())
            }
        }
        // Last resort, so the system does not kill us for not calling startForeground.
        runCatching { startForeground(NOTIFICATION_ID, buildNotification(0)) }
        return false
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int = START_STICKY

    override fun onDestroy() {
        scope?.cancel()
        scope = null
        synchronized(gpsLock) {
            gps?.stop()
            gps = null
        }
        if (started) Status.setServiceRunning(false)
        super.onDestroy()
    }

    private fun buildUploadLoop(): UploadLoop {
        val uploader = Uploader(
            queue = graph.queue,
            settings = graph.settings,
            http = graph.http,
            appVersion = BuildConfig.VERSION_NAME,
            offsets = {
                OffsetRecorder.usablePersisted(graph.dao.offsets()) + graph.sessionClock.offsets()
            },
            currentBoot = { graph.clocks.bootCount() },
        )
        return UploadLoop(
            uploadOnce = { uploader.uploadOnce() },
            remaining = { graph.queue.size() },
            onOutcome = { o: UploadOutcome ->
                Status.recordUpload(System.currentTimeMillis(), o)
                if (o is UploadOutcome.Unauthorized) Log.w(TAG, "upload rejected: 401")
            },
        )
    }

    private suspend fun restartSources(snap: SettingsSnapshot) {
        val s = scope ?: return
        synchronized(gpsLock) {
            if (!s.isActive) return
            gps?.stop()
            val source: GpsSource = if (snap.simulated) FakeGpsSource.fromAssets(this, s) else AndroidGpsSource(this)
            gps = source
            source.start { fix -> s.launch { safely("gps fix") { handleFix(fix) } } }
        }
        restartObd(snap)
    }

    private suspend fun restartObd(snap: SettingsSnapshot = graph.settings.snapshot()) = obdMutex.withLock {
        obdJob?.cancelAndJoin()
        obdJob = null
        if (scope?.isActive != true) return@withLock
        if (!snap.simulated && snap.adapterAddress.isBlank()) {
            Status.setObd(ObdState.Retrying("adapter not configured", 0))
            return@withLock
        }
        val ctx = this
        obdJob = supervisor.launch("obd") {
            // One log per OBD run, so the screen keeps the history across reconnect attempts.
            val elmLog = ElmLog(sink = Status::setObdLog)
            val obd = ObdSource(
                transportFactory = {
                    val inner = if (snap.simulated) FakeElmTransport() else BluetoothElmTransport(ctx, snap.adapterAddress)
                    LoggingElmTransport(inner, elmLog)
                },
                clocks = graph.clocks,
                emit = { record, stamp -> graph.queue.add(record, stamp) },
                sessionProvider = { session.get() },
                protocolStore = graph.protocolStore,
                adapterAddress = snap.adapterAddress,
                protocolPreference = snap.obdProtocol,
            )
            coroutineScope {
                launch { obd.state.collect { Status.setObd(it) } }
                obd.run()
            }
        }
    }

    private suspend fun onResumed() {
        val fresh = Session()
        safely("resumed") {
            emitEvent(fresh, Events.SESSION_START, null)
            emitEvent(fresh, Events.RESUMED, null)
        }
        session.set(fresh)
        uploadLoop?.resetBackoff() // first upload after deep sleep must not wait out an old backoff
        restartObd()
    }

    /** Runs [block]; failures (queue/disk) are logged and recorded instead of crashing the process. */
    private suspend fun safely(what: String, block: suspend () -> Unit) {
        try {
            block()
        } catch (e: CancellationException) {
            throw e
        } catch (e: Exception) {
            Log.w(TAG, "$what failed", e)
            Status.addError("$what: ${e.javaClass.simpleName}: ${e.message ?: ""}".trim())
        }
    }

    private suspend fun handleFix(fix: GpsFix) {
        val stamp = graph.clocks.stamp()
        graph.offsetRecorder.onFix(stamp.bootCount, fix.utcMs, stamp.elapsedMs, fix.simulated)
        Status.setLastFix(fix)
        val sess = session.get()
        graph.queue.add(
            GpsRecord(
                id = UUID.randomUUID().toString(),
                session_id = sess.id,
                seq = sess.nextSeq(),
                ts = 0,
                lat = fix.lat,
                lon = fix.lon,
                acc_m = fix.accM,
                speed_mps = fix.speedMps,
                bearing = fix.bearing,
                alt_m = fix.altM,
            ),
            stamp,
        )
    }

    private suspend fun emitEvent(sess: Session, event: String, detail: String?) {
        val stamp: Stamp = graph.clocks.stamp()
        graph.queue.add(EventRecord(UUID.randomUUID().toString(), sess.id, sess.nextSeq(), 0, event, detail), stamp)
    }

    private fun createChannel() {
        val nm = getSystemService(NotificationManager::class.java)
        nm.createNotificationChannel(
            NotificationChannel(CHANNEL_ID, "Telemetría", NotificationManager.IMPORTANCE_LOW),
        )
    }

    private fun buildNotification(pending: Int): Notification {
        val unauthorized = Status.lastUpload.value?.second is UploadOutcome.Unauthorized
        val text = if (unauthorized) "Token incorrecto (401)" else "Telemetría 307 activa · $pending pendientes"
        return Notification.Builder(this, CHANNEL_ID)
            .setSmallIcon(android.R.drawable.stat_notify_sync)
            .setContentTitle("car-trace")
            .setContentText(text)
            .setOngoing(true)
            .build()
    }

    private fun notify(pending: Int) {
        getSystemService(NotificationManager::class.java).notify(NOTIFICATION_ID, buildNotification(pending))
    }

    private companion object {
        const val TAG = "CarTrace"
        const val CHANNEL_ID = "telemetry"
        const val NOTIFICATION_ID = 307
        const val SLEEP_TICK_MS = 5_000L
        const val NOTIFY_EVERY_MS = 10_000L
    }
}
