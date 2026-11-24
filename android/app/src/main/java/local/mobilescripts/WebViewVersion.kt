package local.mobilescripts

/**
 * Pure helper behind the "WebView too old" decision (no Android classes, so it can be unit tested
 * later). The lowest Chrome major version that runs the launcher frontend is [MIN_CHROME_MAJOR]:
 * the sources and vendor/lit.js use `?.` and `??` (Chrome 80); a Chrome 52 WebView shows a blank page.
 */
object WebViewVersion {
    const val MIN_CHROME_MAJOR = 80

    private val CHROME = Regex("""Chrome/(\d+)""")

    /** The Chrome major version in a WebView user agent, or null when it has none. */
    fun chromeMajor(userAgent: String): Int? = CHROME.find(userAgent)?.groupValues?.get(1)?.toIntOrNull()

    /** Unknown versions are given the benefit of the doubt: the page check still catches a blank page. */
    fun isTooOld(userAgent: String): Boolean = (chromeMajor(userAgent) ?: MIN_CHROME_MAJOR) < MIN_CHROME_MAJOR
}
