// swift-tools-version: 5.9
//
// Lauffähige iOS-Demo im offiziellen .swiftpm-App-Format (Swift
// Playgrounds / Xcode "Open" auf diesen Ordner). Kein .xcodeproj nötig.
//
// In Xcode öffnen: File → Open… → diesen SecureMessengerDemo.swiftpm-Ordner
// auswählen, warten bis die Paketabhängigkeit (swift-sodium) aufgelöst
// ist, dann auf einem iOS-Simulator ausführen.

import PackageDescription

let package = Package(
    name: "SecureMessengerDemo",
    platforms: [.iOS(.v16)],
    products: [
        .iOSApplication(
            name: "SecureMessengerDemo",
            targets: ["AppModule"],
            bundleIdentifier: "com.example.securemessengerdemo",
            teamIdentifier: "",
            displayVersion: "1.0",
            bundleVersion: "1",
            supportedDeviceFamilies: [.pad, .phone]
        )
    ],
    dependencies: [
        .package(url: "https://github.com/jedisct1/swift-sodium.git", from: "0.9.1"),
        .package(url: "https://github.com/emqx/CocoaMQTT.git", from: "2.1.6")
    ],
    targets: [
        .executableTarget(
            name: "AppModule",
            dependencies: [
                .product(name: "Sodium", package: "swift-sodium"),
                .product(name: "CocoaMQTT", package: "CocoaMQTT")
            ],
            path: "Sources"
        )
    ]
)
