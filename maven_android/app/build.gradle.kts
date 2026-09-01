plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

// Generation pin flows in from pins.env via maven_check.sh (-PlitertlmVersion=…).
val litertlmVersion = (project.findProperty("litertlmVersion") as String?) ?: "0.16.1"

android {
    namespace = "dev.relgate.litertlm"
    compileSdk = 35
    defaultConfig {
        applicationId = "dev.relgate.litertlm"
        minSdk = 28
        targetSdk = 35
        versionCode = 1
        versionName = "1"
        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"
    }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions { jvmTarget = "17" }
}

dependencies {
    implementation("com.google.ai.edge.litertlm:litertlm-android:$litertlmVersion")
    // Pinned to a PUBLIC coroutines release on purpose: #3334 reports the AAR
    // was compiled against a coroutines build no public release matches, so the
    // consumer-side version must be an ordinary published one (1.7.3 and 1.9.0
    // both reproduce per the issue).
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-android:1.9.0")
    androidTestImplementation("androidx.test:runner:1.6.2")
    androidTestImplementation("androidx.test.ext:junit:1.2.1")
    androidTestImplementation("junit:junit:4.13.2")
}
