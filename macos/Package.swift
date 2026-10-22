// swift-tools-version: 6.0
import PackageDescription

let package = Package(
    name: "AISADMenuBar",
    platforms: [.macOS(.v14)],
    products: [.executable(name: "AISADMenuBar", targets: ["AISADMenuBar"])],
    targets: [
        .target(name: "AISADCore"),
        .executableTarget(name: "AISADMenuBar", dependencies: ["AISADCore"]),
        .testTarget(name: "AISADCoreTests", dependencies: ["AISADCore"])
    ]
)
