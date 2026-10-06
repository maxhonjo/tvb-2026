import AppKit
import Foundation
import CoreGraphics

// Stream one JSON line per key-down to stdout. Unbuffered so the Python reader
// sees each key immediately (stdout is block-buffered when piped).
setvbuf(stdout, nil, _IONBF, 0)

let iso = ISO8601DateFormatter()

// Keys that produce no (useful) character get a named token instead.
let special: [Int64: String] = [
    36: "<return>", 48: "<tab>", 49: "<space>", 51: "<delete>",
    53: "<escape>", 76: "<enter>", 117: "<forward-delete>",
    115: "<home>", 116: "<pageup>", 119: "<end>", 121: "<pagedown>",
    123: "<left>", 124: "<right>", 125: "<down>", 126: "<up>",
]

func emit(_ key: String) {
    // Frontmost GUI app at the moment of the keypress, so downstream readers can
    // tell which app the text was typed in. Raw metadata; no interpretation here.
    let app = NSWorkspace.shared.frontmostApplication?.localizedName ?? ""
    let payload: [String: Any] = [
        "key": key, "app": app, "timestamp": iso.string(from: Date()),
    ]
    if let data = try? JSONSerialization.data(withJSONObject: payload),
       let line = String(data: data, encoding: .utf8) {
        print(line)
    }
}

// Listen-only tap: observe key-downs without altering or swallowing them.
let callback: CGEventTapCallBack = { _, type, event, _ in
    if type == .keyDown {
        let code = event.getIntegerValueField(.keyboardEventKeycode)
        if let name = special[code] {
            emit(name)
        } else {
            var length = 0
            var chars = [UniChar](repeating: 0, count: 4)
            event.keyboardGetUnicodeString(
                maxStringLength: 4, actualStringLength: &length, unicodeString: &chars)
            if length > 0 {
                emit(String(utf16CodeUnits: chars, count: length))
            }
        }
    }
    return Unmanaged.passUnretained(event)
}

guard let tap = CGEvent.tapCreate(
    tap: .cgSessionEventTap,
    place: .headInsertEventTap,
    options: .listenOnly,
    eventsOfInterest: CGEventMask(1 << CGEventType.keyDown.rawValue),
    callback: callback,
    userInfo: nil
) else {
    FileHandle.standardError.write(
        "cannot create event tap (Input Monitoring / Accessibility not granted)\n"
            .data(using: .utf8)!)
    exit(2)  // DENIED_EXIT in src/mac.py
}

let source = CFMachPortCreateRunLoopSource(kCFAllocatorDefault, tap, 0)
CFRunLoopAddSource(CFRunLoopGetCurrent(), source, .commonModes)
CGEvent.tapEnable(tap: tap, enable: true)
CFRunLoopRun()
