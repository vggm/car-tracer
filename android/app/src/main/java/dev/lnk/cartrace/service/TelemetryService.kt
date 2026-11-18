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
import dev.lnk.cartrace.core.Session
import dev.lnk.cartrace.core.SleepDetector
import dev.lnk.cartrace.core.Stamp
import dev.lnk.cartrace.core.stamp
import dev.lnk.cartrace.gps.AndroidGpsSource
import dev.lnk.cartrace.gps.GpsFix
import dev.lnk.cartrace.gps.GpsSource
import dev.lnk.cartrace.obd.BluetoothElmTransport
import dev.lnk.cartrace.obd.ObdSource
import dev.lnk.cartrace.obd.ObdState
import dev.lnk.cartrace.queue.BootOffset
import dev.lnk.cartrace.settings.SettingsSnapshot
import dev.lnk.cartrace.sim.FakeElmTransport
import dev.lnk.cartrace.sim.FakeGpsSource
import dev.lnk.cartrace.upload.UploadOutcome
import dev.lnk.cartrace.upload.Uploader
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.coroutineScope
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.distinctUntilChanged
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

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onCreate() {
        super.onCreate()
        graph = AppGraph.get(this)
        createChannel()
        try {
            startForeground(
                NOTIFICATION_ID,
                buildNotification(0),
                ServiceInfo.FOREGROUND_SERVICE_TYPE_LOCATION or ServiceInfo.FOREGROUND_SERVICE_TYPE_CONNECTED_DEVICE,
            )
        } catch (e: Exception) {
            Log.e(TAG, "startForeground failed", e)
            Status.addError("startForeground: ${e.javaClass.simpleName}: ${e.message ?: ""}".trim())
            stopSelf()
            return
        }
        val s = CoroutineScope(SupervisorJob() + Dispatchers.Default)
        scope = s
        supervisor = Supervisor(s)
        started = true
        Status.setServiceRunning(true)

        supervisor.launch("session_start") { emitEvent(Events.SESSION_START, null) }
        supervisor.launch("sources") {
            graph.settings.changes
                .map { it.simulated to it.adapterAddress }
                .distinctUntilChanged()
                .collect { restartSources(graph.settings.snapshot()) }
        }
        supervisor.launch("uploader") { uploadLoop().run() }
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

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int = START_STICKY

    override fun onDestroy() {
        gps?.stop()
        gps = null
        scope?.cancel()
        scope = null
        if (started) Status.setServiceRunning(false)
        super.onDestroy()
    }

    private fun uploadLoop(): UploadLoop {
        val uploader = Uploader(
            queue = graph.queue,
            settings = graph.settings,
            http = graph.http,
            appVersion = BuildConfig.VERSION_NAME,
            offsets = {
                graph.dao.offsets().associate { it.bootCount to it.offsetMs } + graph.sessionClock.offsets()
            },
            currentBoot = { graph.clocks.bootCount() },
        )
        return UploadLoop(
            uploadOnce = { uploader.uploadOnce() },
            remaining = { graph.queue.size() },
            onOutcome = { o: UploadOutcome ->
                Status.setLastUpload(System.currentTimeMillis(), o)
                if (o is UploadOutcome.Unauthorized) Log.w(TAG, "upload rejected: 401")
            },
        )
    }

    @Synchronized
    private fun restartSources(snap: SettingsSnapshot) {
        val s = scope ?: return
        gps?.stop()
        val source: GpsSource = if (snap.simulated) FakeGpsSource.fromAssets(this, s) else AndroidGpsSource(this)
        gps = source
        source.start { fix -> s.launch { handleFix(fix) } }
        restartObd(snap)
    }

    @Synchronized
    private fun restartObd(snap: SettingsSnapshot = graph.settings.snapshot()) {
        obdJob?.cancel()
        obdJob = null
        if (!snap.simulated && snap.adapterAddress.isBlank()) {
            Status.setObd(ObdState.Retrying("adapter not configured", 0))
            return
        }
        val ctx = this
        obdJob = supervisor.launch("obd") {
            val obd = ObdSource(
                transportFactory = {
                    if (snap.simulated) FakeElmTransport() else BluetoothElmTransport(ctx, snap.adapterAddress)
                },
                clocks = graph.clocks,
                emit = { record, stamp -> graph.queue.add(record, stamp) },
                sessionProvider = { session.get() },
            )
            coroutineScope {
                launch { obd.state.collect { Status.setObd(it) } }
                obd.run()
            }
        }
    }

    private suspend fun onResumed() {
        session.set(Session())
        emitEvent(Events.SESSION_START, null)
        emitEvent(Events.RESUMED, null)
        restartObd()
    }

    private suspend fun handleFix(fix: GpsFix) {
        val stamp = graph.clocks.stamp()
        graph.sessionClock.onGpsFix(stamp.bootCount, fix.utcMs, stamp.elapsedMs)
        graph.dao.saveOffset(BootOffset(stamp.bootCount, fix.utcMs - stamp.elapsedMs))
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

    private suspend fun emitEvent(event: String, detail: String?) {
        val sess = session.get()
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
