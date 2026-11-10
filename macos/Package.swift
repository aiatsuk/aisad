// swift-tools-version: 6.0
import PackageDescription

let package = Package(
    name: "ASIMenuBar",
    platforms: [.macOS(.v14)],
    products: [.executable(name: "ASIMenuBar", targets: ["ASIMenuBar"])],
    targets: [
        .target(name: "ASICore"),
        .executableTarget(name: "ASIMenuBar", dependencies: ["ASICore"]),
        .testTarget(name: "ASICoreTests", dependencies: ["ASICore"])
    ]
)
