package local.mobilescripts

import java.io.IOException
import java.net.HttpURLConnection
import java.net.ServerSocket
import java.net.URL
import org.json.JSONException
import org.json.JSONObject

/**
 * Calls of the Termux backend's JSON API on loopback. Every method blocks, so call them from a
 * background thread only. Failures are IOExceptions whose text says what went wrong.
 */
class BackendClient(val port: Int) {
    private val baseUrl = "http://127.0.0.1:$port"

    /** The list page, which the WebView loads once the backend is healthy. */
    val listUrl = "$baseUrl/"

    /** GET /api/health; throws unless the backend answers 200. */
    fun checkHealth() {
        request("GET", "/api/health")
    }

    /** POST /api/heartbeat; true while a script runs (`{"running": {...}}`), false for `null`. */
    fun sendHeartbeat(): Boolean {
        val body = request("POST", "/api/heartbeat")
        try {
            return !JSONObject(body).isNull("running")
        } catch (error: JSONException) {
            throw IOException("Heartbeat answer is not the expected JSON: $body", error)
        }
    }

    /** POST /api/shutdown; the backend stops its script and exits. */
    fun shutdown() {
        request("POST", "/api/shutdown")
    }

    private fun request(method: String, path: String): String {
        val connection = URL(baseUrl + path).openConnection() as HttpURLConnection
        try {
            connection.requestMethod = method
            connection.connectTimeout = TIMEOUT_MILLIS
            connection.readTimeout = TIMEOUT_MILLIS
            if (method == "POST") {
                // An explicit empty body, so the request carries Content-Length: 0.
                connection.doOutput = true
                connection.setFixedLengthStreamingMode(0)
            }
            val status = connection.responseCode
            if (status != HttpURLConnection.HTTP_OK) {
                throw IOException("$method $path answered HTTP $status")
            }
            return connection.inputStream.bufferedReader().use { it.readText() }
        } finally {
            connection.disconnect()
        }
    }

    companion object {
        private const val TIMEOUT_MILLIS = 2000

        /** A port the OS reports as free right now; the backend is started on it by Termux. */
        fun pickFreePort(): Int = ServerSocket(0).use { it.localPort }
    }
}
