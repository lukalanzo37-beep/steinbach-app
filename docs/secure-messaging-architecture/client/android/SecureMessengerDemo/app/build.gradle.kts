plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

android {
    namespace = "com.example.securemessenger.demo"
    compileSdk = 34

    defaultConfig {
        applicationId = "com.example.securemessenger.demo"
        minSdk = 26
        targetSdk = 34
        versionCode = 1
        versionName = "1.0"
    }

    buildFeatures {
        compose = true
    }

    composeOptions {
        kotlinCompilerExtensionVersion = "1.5.14"
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    kotlinOptions {
        jvmTarget = "17"
    }
}

dependencies {
    implementation("androidx.core:core-ktx:1.13.1")
    implementation("androidx.activity:activity-compose:1.9.2")
    implementation(platform("androidx.compose:compose-bom:2024.09.02"))
    implementation("androidx.compose.ui:ui")
    implementation("androidx.compose.material3:material3")
    implementation("androidx.compose.ui:ui-tooling-preview")

    // Gleiche NaCl-Bindung wie im produktionsnahen Referenzcode
    // (../E2EECryptoManager.kt): LazySodium bindet libsodium via JNA.
    implementation("com.goterl:lazysodium-android:5.1.0@aar")
    implementation("net.java.dev.jna:jna:5.13.0@aar")

    // MQTT-Transport zum selben öffentlichen Test-Broker wie die Web-Demo
    // (siehe ../../../PROTOCOL.md) -- Platzhalter für den echten
    // "blinden" Relay-Server in backend/src/main.rs.
    implementation("org.eclipse.paho:org.eclipse.paho.client.mqttv3:1.2.5")
}
