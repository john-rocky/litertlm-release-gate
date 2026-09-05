plugins {
    id("com.android.application") version "8.7.3" apply false
    // The consumer Kotlin floor follows the AAR's metadata version and it moves
    // every release: 0.16.1 shipped metadata 2.3.0 (a 2.1.x consumer cannot read
    // it, measured 2026-08-31), and 0.17.0 ships metadata 2.4.0 (a 2.2.x consumer
    // cannot read it: "can read versions up to 2.3.0", measured 2026-09-06).
    // Kotlin 2.4.0 is a public stable release (2026-06-03): a floor finding, not
    // an internal toolchain.
    id("org.jetbrains.kotlin.android") version "2.4.0" apply false
}
