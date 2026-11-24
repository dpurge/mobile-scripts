package local.mobilescripts

import android.app.Activity
import android.content.Intent
import android.content.pm.PackageManager

/** Talks to the Termux app: is it installed, may we use it, and start the backend in it. */
class TermuxLauncher(private val activity: Activity, private val workspaceDir: () -> String) {

    fun isInstalled(): Boolean = try {
        // Needs the <queries> entry for com.termux in the manifest (package visibility).
        @Suppress("DEPRECATION")
        activity.packageManager.getPackageInfo(TERMUX_PACKAGE, 0)
        true
    } catch (error: PackageManager.NameNotFoundException) {
        false
    }

    fun hasRunCommandPermission(): Boolean =
        activity.checkSelfPermission(RUN_COMMAND_PERMISSION) == PackageManager.PERMISSION_GRANTED

    /** Shows the system permission dialog; the answer arrives in the activity's callback. */
    fun requestRunCommandPermission(requestCode: Int) {
        activity.requestPermissions(arrayOf(RUN_COMMAND_PERMISSION), requestCode)
    }

    /**
     * Sends the RUN_COMMAND intent that runs `start.sh <port>` in the background in Termux.
     * Throws (SecurityException when the permission is missing, others from startService); the
     * caller reports it. A Termux that refuses (allow-external-apps) does not throw here: the
     * backend then never answers and the caller's health timeout reports it.
     */
    fun startBackend(port: Int) {
        val workspace = workspaceDir()
        val intent = Intent().apply {
            setClassName(TERMUX_PACKAGE, RUN_COMMAND_SERVICE)
            action = RUN_COMMAND_ACTION
            putExtra("$TERMUX_PACKAGE.RUN_COMMAND_PATH", BASH_PATH)
            putExtra(
                "$TERMUX_PACKAGE.RUN_COMMAND_ARGUMENTS",
                arrayOf("$workspace/launcher/termux/start.sh", port.toString()),
            )
            putExtra("$TERMUX_PACKAGE.RUN_COMMAND_WORKDIR", workspace)
            putExtra("$TERMUX_PACKAGE.RUN_COMMAND_BACKGROUND", true)
        }
        // The activity is in the foreground, so startService is allowed on API 26+; Termux's
        // RunCommandService calls startForeground itself.
        // startService returns null when no such service exists, i.e. Termux has no RunCommandService.
        activity.startService(intent)
            ?: throw IllegalStateException("Termux has no $RUN_COMMAND_SERVICE service (version too old?)")
    }

    companion object {
        const val RUN_COMMAND_PERMISSION = "com.termux.permission.RUN_COMMAND"
        private const val TERMUX_PACKAGE = "com.termux"
        private const val RUN_COMMAND_SERVICE = "com.termux.app.RunCommandService"
        private const val RUN_COMMAND_ACTION = "com.termux.RUN_COMMAND"
        private const val BASH_PATH = "/data/data/com.termux/files/usr/bin/bash"
    }
}
