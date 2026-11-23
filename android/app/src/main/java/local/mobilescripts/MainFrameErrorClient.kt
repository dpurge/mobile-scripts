package local.mobilescripts

import android.webkit.WebResourceError
import android.webkit.WebResourceRequest
import android.webkit.WebResourceResponse
import android.webkit.WebView
import android.webkit.WebViewClient

/**
 * Keeps links inside the WebView (without a WebViewClient they go to the browser app) and reports
 * failed loads of the page itself, so the activity can show its native diagnostic instead of the
 * browser's error page. Errors of sub-resources (images, scripts, API calls) are ignored on purpose.
 * Callbacks arrive on the UI thread.
 */
class MainFrameErrorClient(
    private val onMainFrameError: (url: String, error: String) -> Unit,
) : WebViewClient() {

    override fun onReceivedError(view: WebView, request: WebResourceRequest, error: WebResourceError) {
        if (request.isForMainFrame) {
            onMainFrameError(request.url.toString(), "${error.description} (code ${error.errorCode})")
        }
    }

    override fun onReceivedHttpError(view: WebView, request: WebResourceRequest, errorResponse: WebResourceResponse) {
        if (request.isForMainFrame && errorResponse.statusCode >= HTTP_ERROR_FROM) {
            onMainFrameError(
                request.url.toString(),
                "HTTP ${errorResponse.statusCode} ${errorResponse.reasonPhrase.orEmpty()}".trim(),
            )
        }
    }

    private companion object {
        const val HTTP_ERROR_FROM = 400
    }
}
