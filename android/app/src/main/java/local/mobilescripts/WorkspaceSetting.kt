package local.mobilescripts

import android.content.Context

/**
 * Where the repo is cloned inside Termux. Chosen by the user on the diagnostic screen and kept in
 * the app's preferences, so moving the clone needs no new APK; until then the build-time default
 * [BuildConfig.WORKSPACE_DIR] (`build_apk.py --workspace-dir`) applies.
 */
class WorkspaceSetting(context: Context) {
    private val preferences = context.getSharedPreferences(PREFERENCES_NAME, Context.MODE_PRIVATE)

    fun get(): String = preferences.getString(KEY, null) ?: BuildConfig.WORKSPACE_DIR

    /** Stores the path; returns null on success, or what is wrong with it (nothing is stored then). */
    fun save(path: String): String? {
        val error = validate(path)
        if (error == null) preferences.edit().putString(KEY, normalize(path)).apply()
        return error
    }

    companion object {
        private const val PREFERENCES_NAME = "settings"
        private const val KEY = "workspace_dir"

        /** Pure, for unit tests later. Termux paths are POSIX, so absolute means a leading slash. */
        fun validate(path: String): String? = when {
            path.isBlank() -> "The workspace path is empty."
            !path.trim().startsWith("/") -> "The workspace path must be absolute (start with /), got '${path.trim()}'."
            else -> null
        }

        fun normalize(path: String): String = path.trim().trimEnd('/').ifEmpty { "/" }
    }
}
