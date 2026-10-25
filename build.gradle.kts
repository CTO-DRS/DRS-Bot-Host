// DRS Bot Host - root build configuration.
// Version pins verified against (Oct 2026):
//  - Chaquopy 17.1.0 supports AGP 7.3.x - 9.4.x, minSdk >= 24, Python 3.10-3.15
//    https://chaquo.com/chaquopy/doc/current/android.html
//  - AGP 8.7 requires Gradle >= 8.9
//    https://developer.android.com/build/releases/about-agp
plugins {
    id("com.android.application") version "8.7.3" apply false
    id("org.jetbrains.kotlin.android") version "2.0.21" apply false
    id("org.jetbrains.kotlin.plugin.compose") version "2.0.21" apply false
    id("com.chaquo.python") version "17.1.0" apply false
}
