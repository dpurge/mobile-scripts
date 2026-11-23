package local.mobilescripts

import android.app.Activity
import android.content.pm.PackageManager
import android.os.Bundle
import android.os.SystemClock
import android.view.View
import android.view.ViewGroup
import android.webkit.WebView
import java.io.IOException

/**
 * Native-first host of the launcher. States, in order:
 *
 * 1. status screen "Starting Termux backend...";
 * 2. Termux installed and RUN_COMMAND permission granted (asked for if missing);
 * 3. `start.sh <port>` sent to Termux, then GET /api/health polled for [HEALTH_TIMEOUT_MILLIS];
 * 4. only then the WebView, which loads the list; a heartbeat runs while it is shown;
 * 5. any failure on the way, a backend that stops answering to the heartbeat (3 misses in a row) or a
 *    failed load of the page: the diagnostic screen with Retry (it replaces the WebView). The WebView is never created
 *    before the backend answered, so it can never be empty.
 *
 * Closing the activity (isFinishing) asks the backend to shut down; the watchdog covers a kill.
 */
class MainActivity : Activity() {
    private lateinit var termux: TermuxLauncher
    private lateinit var screens: StatusScreen

    // Bumped by every (re)start, so answers from an abandoned attempt are ignored.
    @Volatile private var attempt = 0
    private var backend: BackendClient? = null
    private var heartbeat: HeartbeatLoop? = null
    private var webView: WebView? = null

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        termux = TermuxLauncher(this)
        screens = StatusScreen(this, onRetry = ::begin)
        begin()
    }

    private fun begin() {
        attempt++
        releaseSession()
        // Retry: do not leave the previous attempt's backend lingering (it may be half started).
        backend?.let(::shutdownInBackground)
        backend = null
        showScreen(screens.status("Starting Termux backend..."))
        if (!termux.isInstalled()) {
            showDiagnostic(START_FAILED, "Termux (package com.termux) is not installed or not visible to this app.")
        } else if (!termux.hasRunCommandPermission()) {
            termux.requestRunCommandPermission(PERMISSION_REQUEST_CODE)
        } else {
            launchBackend()
        }
    }

    override fun onRequestPermissionsResult(
        requestCode: Int,
        permissions: Array<out String>,
        grantResults: IntArray,
    ) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults)
        if (requestCode != PERMISSION_REQUEST_CODE) return
        if (grantResults.firstOrNull() == PackageManager.PERMISSION_GRANTED) {
            launchBackend()
        } else {
            showDiagnostic(
                START_FAILED,
                "The permission ${TermuxLauncher.RUN_COMMAND_PERMISSION} was not granted. " +
                    "Grant it under Android Settings, Apps, Mobile Scripts, Permissions.",
            )
        }
    }

    private fun launchBackend() {
        val client = BackendClient(BackendClient.pickFreePort())
        backend = client
        try {
            termux.startBackend(client.port)
        } catch (error: Exception) {
            showDiagnostic(START_FAILED, "Sending the RUN_COMMAND intent to Termux failed: $error")
            return
        }
        waitForHealth(client, attempt)
    }

    /** Polls /api/health on a background thread; the outcome comes back on the UI thread. */
    private fun waitForHealth(client: BackendClient, id: Int) {
        Thread({
            val deadline = SystemClock.elapsedRealtime() + HEALTH_TIMEOUT_MILLIS
            var lastError = "no attempt made"
            try {
                while (id == attempt && SystemClock.elapsedRealtime() < deadline) {
                    try {
                        client.checkHealth()
                        runOnUiThread { if (id == attempt) showWebView(client, id) }
                        return@Thread
                    } catch (error: IOException) {
                        lastError = error.toString()
                    }
                    Thread.sleep(HEALTH_POLL_MILLIS)
                }
            } catch (interrupted: InterruptedException) {
                return@Thread
            }
            runOnUiThread {
                if (id == attempt) {
                    showDiagnostic(
                        START_FAILED,
                        "GET ${client.listUrl}api/health got no answer within " +
                            "${HEALTH_TIMEOUT_MILLIS / 1000} s. Last error: $lastError",
                    )
                }
            }
        }, "health-poll").start()
    }

    private fun showWebView(client: BackendClient, id: Int) {
        val view = WebView(this).apply {
            layoutParams = ViewGroup.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.MATCH_PARENT,
            )
            // Without a WebViewClient, link navigation is handed to the browser app.
            webViewClient = MainFrameErrorClient { url, error ->
                // Posted: the WebView is destroyed by showDiagnostic, not inside its own callback.
                post { if (id == attempt) showDiagnostic(PAGE_FAILED, "Loading $url failed: $error") }
            }
            settings.javaScriptEnabled = true
            settings.domStorageEnabled = true
            settings.builtInZoomControls = false
            settings.displayZoomControls = false
        }
        webView = view
        showScreen(view)
        view.loadUrl(client.listUrl)
        heartbeat = HeartbeatLoop(
            client,
            onResult = { isScriptRunning ->
                runOnUiThread { if (id == attempt) returnToListIfStopped(client, isScriptRunning) }
            },
            onGaveUp = { error ->
                runOnUiThread {
                    if (id == attempt) showDiagnostic(BACKEND_STOPPED, "Heartbeat failed 3 times in a row. Last error: $error")
                }
            },
        ).also { it.start() }
    }

    /** The script stopped itself (or crashed): show the list again. */
    private fun returnToListIfStopped(client: BackendClient, isScriptRunning: Boolean) {
        val view = webView ?: return
        nextUrl(view.url, isScriptRunning, client.listUrl)?.let { view.loadUrl(it) }
    }

    private fun showDiagnostic(headline: String, failure: String) {
        showScreen(screens.diagnostic(headline, failure))
        releaseSession()
    }

    private fun showScreen(screen: View) {
        setContentView(screen)
    }

    /** Stops the heartbeat and drops the WebView of the previous attempt. */
    private fun releaseSession() {
        heartbeat?.stop()
        heartbeat = null
        webView?.let { (it.parent as? ViewGroup)?.removeView(it); it.destroy() }
        webView = null
    }

    /** Best effort and short-lived; if the process dies first the watchdog ends the backend. */
    private fun shutdownInBackground(client: BackendClient) {
        Thread({
            try {
                client.shutdown()
            } catch (error: IOException) {
                // Backend already gone or never started; nothing left to stop.
            }
        }, "shutdown").start()
    }

    override fun onDestroy() {
        if (isFinishing) {
            heartbeat?.stop()
            backend?.let(::shutdownInBackground)
        }
        releaseSession()
        super.onDestroy()
    }

    private companion object {
        const val PERMISSION_REQUEST_CODE = 1
        const val START_FAILED = "Could not start the Termux backend"
        const val BACKEND_STOPPED = "The backend stopped answering"
        const val PAGE_FAILED = "The page could not be loaded"
        const val HEALTH_TIMEOUT_MILLIS = 30_000L
        const val HEALTH_POLL_MILLIS = 500L
    }
}
