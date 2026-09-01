plugins {
    id("com.android.application") version "8.7.3" apply false
    // 2.2.x is the floor for litertlm-android 0.16.1: the AAR ships Kotlin
    // metadata 2.3.0, which a 2.1.x consumer cannot read (measured 2026-08-31;
    // see google-ai-edge/LiteRT-LM#1972 for the metadata-version history).
    id("org.jetbrains.kotlin.android") version "2.2.10" apply false
}
