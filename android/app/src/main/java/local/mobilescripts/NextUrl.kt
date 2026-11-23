package local.mobilescripts

import java.net.URI
import java.net.URISyntaxException

/**
 * Where the WebView should go after a heartbeat, or null to stay. Same behaviour as `next_url` in
 * `launcher/desktop/host.py`:
 *
 * - a null [currentUrl] (page not loaded yet) returns null;
 * - a running script returns null;
 * - otherwise, when the script has stopped (it ended itself or crashed), returns [listUrl] unless
 *   [currentUrl] already is the list page. That comparison looks at scheme, host, port and path only,
 *   so a query or a fragment does not count as another page.
 *
 * Kept pure, so it is easy to unit test.
 */
fun nextUrl(currentUrl: String?, isScriptRunning: Boolean, listUrl: String): String? =
    if (currentUrl == null || isScriptRunning || isListPage(currentUrl, listUrl)) null else listUrl

private data class UrlIdentity(val scheme: String?, val host: String?, val port: Int, val path: String)

private fun identityOf(url: String): UrlIdentity? =
    try {
        val parsed = URI(url)
        UrlIdentity(parsed.scheme, parsed.host, parsed.port, parsed.rawPath.ifEmpty { "/" })
    } catch (error: URISyntaxException) {
        null
    }

/** A URL that cannot be parsed is compared as a plain string. */
private fun isListPage(currentUrl: String, listUrl: String): Boolean {
    val current = identityOf(currentUrl)
    val list = identityOf(listUrl)
    return if (current != null && list != null) current == list else currentUrl == listUrl
}
