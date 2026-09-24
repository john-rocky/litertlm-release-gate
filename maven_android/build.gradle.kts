plugins {
    id("com.android.application") version "8.7.3" apply false
    // The consumer Kotlin floor follows the AAR's metadata version (a Kotlin
    // compiler reads metadata one minor version above its own) and it moves
    // every release: 0.16.1 shipped metadata 2.3.0 (a 2.1.x consumer cannot read
    // it, measured 2026-08-31; floor 2.2), and 0.17.0 / 0.17.1 ship metadata
    // 2.4.0 (a 2.2.x consumer cannot read it: "can read versions up to 2.3.0",
    // measured 2026-09-06; the Kotlin plugin at 2.3.21 passes, measured
    // 2026-09-25, so the floor is 2.3, not 2.4 as first recorded). The harness
    // pins the current stable release; the floor is one minor below the metadata.
    id("org.jetbrains.kotlin.android") version "2.4.0" apply false
}
