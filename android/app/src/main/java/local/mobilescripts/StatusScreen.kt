package local.mobilescripts

import android.app.Activity
import android.graphics.Color
import android.graphics.Typeface
import android.util.TypedValue
import android.view.View
import android.view.ViewGroup
import android.widget.Button
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView

/**
 * The native full-screen views shown instead of the WebView: a status line while the backend
 * starts, and a diagnostic with a Retry button when something fails. Full width and height,
 * text of at least 18sp (15sp for the secondary lines).
 */
class StatusScreen(
    private val activity: Activity,
    private val currentWorkspace: () -> String,
    private val onRetry: (workspace: String) -> Unit,
) {

    /** A status line, for example "Starting Termux backend...". */
    fun status(message: String): ScrollView = screen(
        text(message, BASE_SP, bold = true),
    )

    /** Why the page opens in the browser, with a button to open it again. */
    fun browserHandoff(message: String, onOpen: () -> Unit): ScrollView = screen(
        text(message, BASE_SP),
        button("Open in browser", onOpen),
    )

    /** A headline, the concrete failure, the likely causes and a Retry button. */
    fun diagnostic(headline: String, failure: String): ScrollView {
        val workspace = EditText(activity).apply {
            setText(currentWorkspace())
            setSingleLine()
            setTextSize(TypedValue.COMPLEX_UNIT_SP, BASE_SP)
        }
        val retry = button("Retry") { onRetry(workspace.text.toString()) }
        return screen(
            text(headline, BASE_SP, bold = true),
            text(failure, BASE_SP, color = ERROR_COLOR),
            text(WORKSPACE_LABEL, BASE_SP, bold = true),
            workspace,
            text(CAUSES_HEADING, BASE_SP, bold = true),
            text(causes(), SECONDARY_SP),
            retry,
        )
    }

    private fun button(label: String, onClick: () -> Unit) = Button(activity).apply {
        text = label
        setTextSize(TypedValue.COMPLEX_UNIT_SP, BASE_SP)
        minimumHeight = dp(MIN_TOUCH_DP)
        setOnClickListener { onClick() }
    }

    private fun causes(): String = """
        1. Termux (F-Droid build) is not installed.
        2. allow-external-apps=true is missing in ~/.termux/termux.properties in Termux (or termux-reload-settings was not run after adding it).
        3. The RUN_COMMAND permission is not granted to this app (Android Settings, Apps, Mobile Scripts, Permissions, Additional permissions).
        4. The repo is not cloned at ${currentWorkspace()} (change the path above if you moved it, then Retry).
        5. python is not installed in Termux (pkg install python).

        Logs in Termux: ${'$'}HOME/launcher-backend.log and ${'$'}HOME/launcher-backend.start-error.log
    """.trimIndent()

    private fun screen(vararg views: View): ScrollView {
        val column = LinearLayout(activity).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(PADDING_DP), dp(PADDING_DP), dp(PADDING_DP), dp(PADDING_DP))
            views.forEach { addView(it, rowParams()) }
        }
        return ScrollView(activity).apply {
            layoutParams = ViewGroup.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.MATCH_PARENT,
            )
            addView(column)
        }
    }

    private fun text(
        message: String,
        sizeSp: Float,
        bold: Boolean = false,
        color: Int? = null,
    ) = TextView(activity).apply {
        text = message
        setTextSize(TypedValue.COMPLEX_UNIT_SP, sizeSp)
        // Selectable, so the failure text can be copied into a bug report.
        setTextIsSelectable(true)
        if (bold) setTypeface(typeface, Typeface.BOLD)
        if (color != null) setTextColor(color)
    }

    private fun rowParams() = LinearLayout.LayoutParams(
        ViewGroup.LayoutParams.MATCH_PARENT,
        ViewGroup.LayoutParams.WRAP_CONTENT,
    ).apply { bottomMargin = dp(PADDING_DP) }

    private fun dp(value: Int): Int =
        (value * activity.resources.displayMetrics.density).toInt()

    private companion object {
        const val BASE_SP = 18f
        const val SECONDARY_SP = 15f
        const val MIN_TOUCH_DP = 48
        const val PADDING_DP = 16
        const val CAUSES_HEADING = "Likely causes"
        const val WORKSPACE_LABEL = "Workspace: where the repo is cloned in Termux"
        val ERROR_COLOR = Color.rgb(0xB0, 0x00, 0x20)
    }
}
