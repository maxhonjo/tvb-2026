import AppKit
import Foundation

// Stream one JSON line per GUI-app event to stdout. Unbuffered so the Python
// reader sees each line immediately (stdout is block-buffered when piped).
setvbuf(stdout, nil, _IONBF, 0)

let iso = ISO8601DateFormatter()

func emit(_ event: String, _ app: NSRunningApplication) {
    let payload: [String: Any] = [
        "event": event,
        "name": app.localizedName ?? "",
        "id": app.bundleIdentifier ?? "",
        "pid": app.processIdentifier,
        "timestamp": iso.string(from: Date()),
    ]
    if let data = try? JSONSerialization.data(withJSONObject: payload),
       let line = String(data: data, encoding: .utf8) {
        print(line)
    }
}

let center = NSWorkspace.shared.notificationCenter

func observe(_ name: NSNotification.Name, as event: String) {
    center.addObserver(forName: name, object: nil, queue: nil) { note in
        if let app = note.userInfo?[NSWorkspace.applicationUserInfoKey]
            as? NSRunningApplication {
            emit(event, app)
        }
    }
}

observe(NSWorkspace.didLaunchApplicationNotification, as: "opened")
observe(NSWorkspace.didTerminateApplicationNotification, as: "closed")
observe(NSWorkspace.didActivateApplicationNotification, as: "activated")

RunLoop.main.run()
