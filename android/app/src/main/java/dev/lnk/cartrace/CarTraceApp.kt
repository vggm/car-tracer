package dev.lnk.cartrace

import android.app.Application
import dev.lnk.cartrace.diag.PrefsPendingDiagStore
import dev.lnk.cartrace.diag.installCrashHandler

/** Installs the crash handler as early as possible so a crash is reported on the next start. */
class CarTraceApp : Application() {
    override fun onCreate() {
        super.onCreate()
        installCrashHandler(PrefsPendingDiagStore(this), Thread.getDefaultUncaughtExceptionHandler())
    }
}
