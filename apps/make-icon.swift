// Draws a Boku-style app icon: one white Mincho glyph on a red rounded square.
// Usage: swift apps/make-icon.swift <glyph> <out.png>
import AppKit

let args = CommandLine.arguments
guard args.count == 3 else {
    FileHandle.standardError.write("usage: make-icon.swift <glyph> <out.png>\n".data(using: .utf8)!)
    exit(1)
}
let glyph = args[1]
let size: CGFloat = 1024
let inset: CGFloat = 100  // transparent margin, as macOS icons have
let radius: CGFloat = 185

let rep = NSBitmapImageRep(
    bitmapDataPlanes: nil, pixelsWide: Int(size), pixelsHigh: Int(size),
    bitsPerSample: 8, samplesPerPixel: 4, hasAlpha: true, isPlanar: false,
    colorSpaceName: .deviceRGB, bytesPerRow: 0, bitsPerPixel: 0)!
NSGraphicsContext.current = NSGraphicsContext(bitmapImageRep: rep)
let ctx = NSGraphicsContext.current!.cgContext

let square = CGRect(x: inset, y: inset, width: size - 2 * inset, height: size - 2 * inset)
ctx.addPath(CGPath(roundedRect: square, cornerWidth: radius, cornerHeight: radius, transform: nil))
ctx.setFillColor(NSColor(srgbRed: 0.784, green: 0.290, blue: 0.180, alpha: 1).cgColor)
ctx.fillPath()

let fontSize: CGFloat = 620
let font = NSFont(name: "ToppanBunkyuMidashiMinchoStdN-ExtraBold", size: fontSize)
    ?? NSFont(name: "HiraMinProN-W6", size: fontSize)
    ?? NSFont.boldSystemFont(ofSize: fontSize)
let line = CTLineCreateWithAttributedString(NSAttributedString(
    string: glyph, attributes: [.font: font, .foregroundColor: NSColor.white]))
// Centre on the ink, not the advance box, so the glyph sits optically centred.
let ink = CTLineGetImageBounds(line, ctx)
ctx.textPosition = CGPoint(x: size / 2 - ink.midX, y: size / 2 - ink.midY)
CTLineDraw(line, ctx)

try! rep.representation(using: .png, properties: [:])!.write(to: URL(fileURLWithPath: args[2]))
