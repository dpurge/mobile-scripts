package local.mobilescripts

import android.app.Activity
import android.content.pm.PackageManager
import android.content.ActivityNotFoundException
import android.content.Intent
import android.net.Uri
import android.os.Bundle
import android.os.SystemClock
import android.view.View
import android.view.ViewGroup
import android.webkit.ConsoleMessage
import android.webkit.WebChromeClient
import android.webkit.WebSettings
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
    private lateinit var workspace: WorkspaceSetting

    // Bumped by every (re)start, so answers from an abandoned attempt are ignored.
    @Volatile private var attempt = 0
    private var backend: BackendClient? = null
    private var heartbeat: HeartbeatLoop? = null
    private var webView: WebView? = null

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        workspace = WorkspaceSetting(this)
        termux = TermuxLauncher(this, workspace::get)
        screens = StatusScreen(this, currentWorkspace = workspace::get, onRetry = ::retryWith)
        begin()
    }

    /** Retry with the workspace path typed on the diagnostic screen. */
    private fun retryWith(workspacePath: String) {
        val error = workspace.save(workspacePath)
        if (error == null) begin() else showDiagnostic(START_FAILED, error)
    }

    private fun begin() {
        attempt++
        releaseSession()
        // Retry: do not leave the previous attempt's backend lingering (it may be half started).
        backend?.let(::shutdownInBackground)
        backend = null
        showScreen(screens.status("Starting Termux backend...\n${workspace.get()}"))
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
        val userAgent = WebSettings.getDefaultUserAgent(this)
        if (WebViewVersion.isTooOld(userAgent)) {
            showBrowserHandoff(client, id, userAgent)
            return
        }
        // The last JavaScript error of the page, for the diagnostic when the list does not appear.
        var lastConsoleError = "none reported"
        val view = WebView(this).apply {
            layoutParams = ViewGroup.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.MATCH_PARENT,
            )
            // Without a WebViewClient, link navigation is handed to the browser app.
            webViewClient = MainFrameErrorClient(onMainFrameError = { url, error ->
                // Posted: the WebView is destroyed by showDiagnostic, not inside its own callback.
                post { if (id == attempt) showDiagnostic(PAGE_FAILED, "Loading $url failed: $error") }
            }, onPageLoaded = { url ->
                // A page that loads but whose scripts fail (an old WebView that cannot parse the
                // modules) stays blank and raises no load error, so ask the page itself.
                if (url == client.listUrl) postDelayed({ checkListRendered(client, id, lastConsoleError) }, LIST_CHECK_DELAY_MILLIS)
            })
            webChromeClient = object : WebChromeClient() {
                override fun onConsoleMessage(message: ConsoleMessage): Boolean {
                    if (message.messageLevel() == ConsoleMessage.MessageLevel.ERROR) {
                        lastConsoleError = "${message.message()} (${message.sourceId()}:${message.lineNumber()})"
                    }
                    return true
                }
            }
            settings.javaScriptEnabled = true
            settings.domStorageEnabled = true
            settings.builtInZoomControls = false
            settings.displayZoomControls = false
        }
        webView = view
        showScreen(view)
        view.loadUrl(client.listUrl)
        startHeartbeat(client, id)
    }

    private fun startHeartbeat(client: BackendClient, id: Int) {
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

    /**
     * The device's WebView is too old for the frontend (Android 7 ships Chrome 52), so the list opens
     * in the browser instead. This activity stays as the owner of the backend: the heartbeat keeps it
     * alive and closing this app stops it. There is no WebView, so a script that stops itself cannot
     * send the browser back to the list; the user reopens it with the button.
     */
    private fun showBrowserHandoff(client: BackendClient, id: Int, userAgent: String) {
        showScreen(screens.browserHandoff(
            "The WebView of this device is too old (Chrome ${WebViewVersion.chromeMajor(userAgent)}, " +
                "needs ${WebViewVersion.MIN_CHROME_MAJOR} or newer), so the app opens in your browser at " +
                "${client.listUrl}\n\nKeep this app open: closing it stops the backend.",
            onOpen = { openInBrowser(client.listUrl) },
        ))
        startHeartbeat(client, id)
        openInBrowser(client.listUrl)
    }

    private fun openInBrowser(url: String) {
        try {
            startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(url)))
        } catch (error: ActivityNotFoundException) {
            showDiagnostic(PAGE_FAILED, "No browser app can open $url: $error")
        }
    }

    /** The list page defines <app-list> when its scripts ran; if it is missing the page is blank. */
    private fun checkListRendered(client: BackendClient, id: Int, lastConsoleError: String) {
        val view = webView ?: return
        if (id != attempt || view.url != client.listUrl) return
        view.evaluateJavascript("!!(window.customElements && customElements.get('app-list'))") { answer ->
            if (id == attempt && answer != "true") {
                showDiagnostic(
                    PAGE_BLANK,
                    "The page loaded but its scripts did not run, so nothing is shown. " +
                        "WebView: ${view.settings.userAgentString}. Last JavaScript error: $lastConsoleError. " +
                        "Update Android System WebView (or Chrome) in the app store, then Retry.",
                )
            }
        }
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
        const val PAGE_BLANK = "The page is blank"
        const val LIST_CHECK_DELAY_MILLIS = 2_000L
        const val HEALTH_TIMEOUT_MILLIS = 30_000L
        const val HEALTH_POLL_MILLIS = 500L
    }
}
