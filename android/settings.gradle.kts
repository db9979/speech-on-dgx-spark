// The Android app "Spark": a thin shell around the Spark's page (plan plaene/handy-wie-app.md 4a).
// Built and signed by .github/workflows/android.yml, served by the Spark itself (app/panel/android.py).
pluginManagement {
    repositories {
        google()
        mavenCentral()
        gradlePluginPortal()
    }
}
dependencyResolutionManagement {
    repositoriesMode.set(RepositoriesMode.FAIL_ON_PROJECT_REPOS)
    repositories {
        google()
        mavenCentral()
    }
}
rootProject.name = "Spark"
include(":app")
