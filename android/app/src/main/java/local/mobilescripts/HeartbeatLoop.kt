package local.mobilescripts

import android.util.Log
import java.io.IOException

/**
 * Sends a heartbeat every [PERIOD_MILLIS] on its own thread until [stop]. The backend's watchdog
 * ends the backend about 15 s after the last one, which also covers an activity that never got
 * to call [BackendClient.shutdown].
 *
 * After [MAX_FAILURES_IN_A_ROW] failed beats (about 9 s) the loop stops itself and calls
 * [onGaveUp] with the last error. Both callbacks run on the heartbeat thread, and neither is called after [stop].
 */
class HeartbeatLoop(
    private val client: BackendClient,
    private val onResult: (isScriptRunning: Boolean) -> Unit,
    private val onGaveUp: (error: String) -> Unit,
) {
    @Volatile private var isStopped = false
    private val failures = ConsecutiveFailures(MAX_FAILURES_IN_A_ROW)
    private val thread = Thread({ loop() }, "heartbeat")

    fun start() {
        thread.start()
    }

    fun stop() {
        isStopped = true
        thread.interrupt()
    }

    private fun loop() {
        try {
            while (!isStopped) {
                try {
                    val isScriptRunning = client.sendHeartbeat()
                    failures.recordSuccess()
                    // stop() may have run while the request was in flight; its result is stale.
                    if (isStopped) return
                    onResult(isScriptRunning)
                } catch (error: IOException) {
                    Log.w(TAG, "Heartbeat failed: ${error.message}")
                    if (isStopped) return
                    if (failures.recordFailure()) {
                        isStopped = true
                        onGaveUp(error.toString())
                        return
                    }
                }
                Thread.sleep(PERIOD_MILLIS)
            }
        } catch (interrupted: InterruptedException) {
            return
        }
    }

    private companion object {
        const val TAG = "HeartbeatLoop"
        const val PERIOD_MILLIS = 3000L
        const val MAX_FAILURES_IN_A_ROW = 3
    }
}
