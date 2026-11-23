plugins {
    id("com.android.application")
}

// Directory of the repo clone inside Termux, handed to Termux as the working directory and as the
// location of launcher/termux/start.sh. Override with: gradle -PworkspaceDir=/some/path
// (build_apk.py --workspace-dir does this).
val workspaceDir: String = providers.gradleProperty("workspaceDir")
    .getOrElse("/data/data/com.termux/files/home/mobile-scripts")

android {
    namespace = "local.mobilescripts"
    compileSdk = 34

    defaultConfig {
        applicationId = "local.mobilescripts"
        minSdk = 24
        targetSdk = 34
        versionCode = 1
        versionName = "0.1"
        buildConfigField("String", "WORKSPACE_DIR", "\"$workspaceDir\"")
    }

    buildFeatures {
        buildConfig = true
    }
}
