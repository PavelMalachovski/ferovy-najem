// Renders the "Dům a fajfka" app icon (1024×1024, opaque) in light, dark and tinted variants.
// Usage: swift scripts/render_app_icon.swift FerovyNajem/Resources/Assets.xcassets/AppIcon.appiconset
import CoreGraphics
import Foundation
import ImageIO
import UniformTypeIdentifiers

struct Palette {
    let background: CGColor
    let house: CGColor
    let check: CGColor
}

func rgb(_ hex: UInt32) -> CGColor {
    CGColor(
        srgbRed: CGFloat((hex >> 16) & 0xFF) / 255,
        green: CGFloat((hex >> 8) & 0xFF) / 255,
        blue: CGFloat(hex & 0xFF) / 255,
        alpha: 1
    )
}

func render(_ p: Palette, to url: URL) {
    let size = 1024
    let ctx = CGContext(
        data: nil, width: size, height: size, bitsPerComponent: 8, bytesPerRow: 0,
        space: CGColorSpace(name: CGColorSpace.sRGB)!,
        bitmapInfo: CGImageAlphaInfo.noneSkipLast.rawValue
    )!
    // SVG coordinates: origin top-left.
    ctx.translateBy(x: 0, y: CGFloat(size))
    ctx.scaleBy(x: 1, y: -1)

    ctx.setFillColor(p.background)
    ctx.fill(CGRect(x: 0, y: 0, width: size, height: size))

    // House: M512 230 L800 470 V790 H224 V470 Z, filled + 48 px round-joined stroke.
    let house = CGMutablePath()
    house.move(to: CGPoint(x: 512, y: 230))
    house.addLine(to: CGPoint(x: 800, y: 470))
    house.addLine(to: CGPoint(x: 800, y: 790))
    house.addLine(to: CGPoint(x: 224, y: 790))
    house.addLine(to: CGPoint(x: 224, y: 470))
    house.closeSubpath()
    ctx.addPath(house)
    ctx.setFillColor(p.house)
    ctx.setStrokeColor(p.house)
    ctx.setLineWidth(48)
    ctx.setLineJoin(.round)
    ctx.drawPath(using: .fillStroke)

    // Check: M372 590 L470 688 L660 498, 76 px round caps/joins.
    let check = CGMutablePath()
    check.move(to: CGPoint(x: 372, y: 590))
    check.addLine(to: CGPoint(x: 470, y: 688))
    check.addLine(to: CGPoint(x: 660, y: 498))
    ctx.addPath(check)
    ctx.setStrokeColor(p.check)
    ctx.setLineWidth(76)
    ctx.setLineCap(.round)
    ctx.setLineJoin(.round)
    ctx.strokePath()

    let image = ctx.makeImage()!
    let dest = CGImageDestinationCreateWithURL(url as CFURL, UTType.png.identifier as CFString, 1, nil)!
    CGImageDestinationAddImage(dest, image, nil)
    precondition(CGImageDestinationFinalize(dest), "failed to write \(url.path)")
}

let out = URL(fileURLWithPath: CommandLine.arguments[1])
let blue = rgb(0x0B5FD3)
render(Palette(background: blue, house: rgb(0xFFFFFF), check: blue),
       to: out.appendingPathComponent("AppIcon.png"))
// Dark: dark ground, house in a lighter blue so it doesn't glare at night.
let night = rgb(0x0E1726)
render(Palette(background: night, house: rgb(0x5AA2FF), check: night),
       to: out.appendingPathComponent("AppIcon-dark.png"))
// Tinted: grayscale; the system applies the user's tint.
let black = rgb(0x000000)
render(Palette(background: black, house: rgb(0xFFFFFF), check: black),
       to: out.appendingPathComponent("AppIcon-tinted.png"))
