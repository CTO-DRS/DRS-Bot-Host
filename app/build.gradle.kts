plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
    id("org.jetbrains.kotlin.plugin.compose")
    id("com.chaquo.python")
}

android {
    namespace = "com.drsbot.host"
    compileSdk = 35

    defaultConfig {
        applicationId = "com.drsbot.host"
        minSdk = 26          // Chaquopy requires >= 24; 26 enables modern notification APIs
        targetSdk = 35
        versionCode = 8
        versionName = "1.7.0"

        // Chaquopy requirement: explicit ABI filters (it ships a native
        // CPython runtime per ABI). Python 3.12 wheels exist only for
        // arm64-v8a + x86_64 (Chaquopy dropped 32-bit ARM); x86_64 covers
        // emulators.
        ndk {
            abiFilters.addAll(listOf("arm64-v8a", "x86_64"))
        }
    }

    buildTypes {
        release {
            isMinifyEnabled = false
            proguardFiles(
                getDefaultProguardFile("proguard-android-optimize.txt"),
                "proguard-rules.pro",
            )
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
        compose = true
        buildConfig = true
    }
}

chaquopy {
    defaultConfig {
        // Embedded Python runtime inside the APK.
        // NOTE: the machine that builds the APK must have a matching
        // `python3` on PATH (buildPython); on GitHub Actions ubuntu runners
        // this is preinstalled.
        version = "3.12"
        // To bake bot pip dependencies into the APK (build-time install):
        // pip { install("requests") }
    }
}

dependencies {
    val composeBom = platform("androidx.compose:compose-bom:2024.12.01")
    implementation(composeBom)

    implementation("androidx.core:core-ktx:1.15.0")
    implementation("androidx.appcompat:appcompat:1.6.1")
    implementation("androidx.activity:activity-compose:1.9.3")
    implementation("androidx.lifecycle:lifecycle-runtime-ktx:2.8.7")
    implementation("androidx.lifecycle:lifecycle-viewmodel-compose:2.8.7")
    implementation("androidx.lifecycle:lifecycle-runtime-compose:2.8.7")
    implementation("androidx.lifecycle:lifecycle-service:2.8.7")
    implementation("androidx.navigation:navigation-compose:2.8.5")
    implementation("androidx.datastore:datastore-preferences:1.1.1")
    implementation("androidx.documentfile:documentfile:1.0.1")

    implementation("androidx.compose.ui:ui")
    implementation("androidx.compose.ui:ui-graphics")
    implementation("androidx.compose.ui:ui-tooling-preview")
    implementation("androidx.compose.material3:material3")
    implementation("androidx.compose.material:material-icons-extended")

    debugImplementation("androidx.compose.ui:ui-tooling")

    testImplementation("junit:junit:4.13.2")
}

// --------------------------------------------------------------------- //
// Sync the verified python-runtime core into the APK's python sources.  //
// Canonical code lives in /python-runtime (tested by CI with pytest);   //
// it is copied into src/main/python at build time so Chaquopy packages  //
// it into the APK. This directory is git-ignored.                       //
// --------------------------------------------------------------------- //
// Gradle 8 forbids touching project state from doFirst (state-lock error),
// so the wipe is a proper Delete task ordered before the Copy.
val cleanPythonSources = tasks.register<Delete>("cleanPythonSources") {
    delete(layout.projectDirectory.dir("src/main/python"))
}

val syncPythonRuntime = tasks.register<Copy>("syncPythonRuntime") {
    dependsOn(cleanPythonSources)
    from(rootProject.file("python-runtime/src"))
    into(layout.projectDirectory.dir("src/main/python"))
}

// preBuild covers the classic path; Chaquopy's merge<Variant>PythonSources
// reads src/main/python directly, so Gradle 8+ requires the dependency to be
// declared explicitly (implicit-dependency validation error otherwise).
tasks.matching { task ->
    task.name == "preBuild" ||
        (task.name.startsWith("merge") && task.name.endsWith("PythonSources"))
}.configureEach {
    dependsOn(syncPythonRuntime)
}
