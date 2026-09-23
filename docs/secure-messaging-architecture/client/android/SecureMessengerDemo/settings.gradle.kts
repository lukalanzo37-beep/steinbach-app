// In Android Studio öffnen: File → Open… → diesen SecureMessengerDemo-Ordner
// auswählen und den Gradle-Sync abwarten.

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

rootProject.name = "SecureMessengerDemo"
include(":app")
