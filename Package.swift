// swift-tools-version:5.9
// SwiftPM 版工程：让 xtool / swift build 也能在非 Xcode 环境下编译同一个 App。
// XcodeGen 的 project.yml 仍然保留，CI 走的是那条路；两者共用 Sources 目录。
import PackageDescription

let package = Package(
    name: "Shiyin",
    platforms: [
        .iOS(.v17),
    ],
    targets: [
        .executableTarget(
            name: "Shiyin",
            path: "Sources"
        ),
    ]
)
