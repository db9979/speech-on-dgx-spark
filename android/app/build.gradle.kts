import java.util.Properties

plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

val version = Properties().apply { rootProject.file("version.properties").inputStream().use { load(it) } }
// the signing key only exists in CI (repository secrets); without it the release stays unsigned
val keystore: String? = System.getenv("SPARK_KEYSTORE")

android {
    namespace = "io.github.db9979.spark"
    compileSdk = 35

    defaultConfig {
        applicationId = "io.github.db9979.spark"
        minSdk = 29
        targetSdk = 35
        versionCode = version.getProperty("code").toInt()
        versionName = version.getProperty("name")
    }

    signingConfigs {
        if (keystore != null) {
            create("release") {
                storeFile = file(keystore)
                storePassword = System.getenv("SPARK_KEYSTORE_PASSWORD")
                keyAlias = System.getenv("SPARK_KEY_ALIAS") ?: "spark"
                keyPassword = System.getenv("SPARK_KEYSTORE_PASSWORD")
            }
        }
    }

    buildTypes {
        release {
            isMinifyEnabled = false
            if (keystore != null) signingConfig = signingConfigs.getByName("release")
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions {
        jvmTarget = "17"
    }
    buildFeatures {
        buildConfig = true
    }
}
