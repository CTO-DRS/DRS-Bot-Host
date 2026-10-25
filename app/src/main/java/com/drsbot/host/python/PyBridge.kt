package com.drsbot.host.python

import android.content.Context
import com.chaquo.python.PyObject
import com.chaquo.python.Python
import com.chaquo.python.android.AndroidPlatform
import java.io.File

/**
 * Single access point to the embedded CPython runtime (Chaquopy).
 *
 * - `ensure()` starts the interpreter once and calls
 *   `drs_host.host_api.configure(filesDir/botdata)`.
 * - `dumps()` converts Python return values to JSON strings, which the Kotlin
 *   data layer parses with `org.json`. This keeps the JNI surface minimal and
 *   avoids fragile deep PyObject -> Java conversion.
 */
object PyBridge {

    @Volatile
    private var configured: Boolean = false

    fun ensure(appContext: Context) {
        if (!Python.isStarted()) {
            synchronized(this) {
                if (!Python.isStarted()) {
                    Python.start(AndroidPlatform(appContext.applicationContext))
                }
            }
        }
        if (!configured) {
            synchronized(this) {
                if (!configured) {
                    val dataDir = File(appContext.filesDir, "botdata")
                    dataDir.mkdirs()
                    api().callAttr("configure", dataDir.absolutePath)
                    configured = true
                }
            }
        }
    }

    fun api(): PyObject = Python.getInstance().getModule("drs_host.host_api")

    /** Serialize any JSON-serializable PyObject into a JSON string. */
    fun dumps(value: PyObject): String =
        Python.getInstance()
            .getModule("json")
            .callAttr("dumps", value)
            .toString()
}
