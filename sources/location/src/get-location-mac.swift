import CoreLocation
import Foundation

let settingsHint = "System Settings > Privacy & Security > Location Services"

func fail(_ message: String) -> Never {
    FileHandle.standardError.write("\(message)\n".data(using: .utf8)!)
    exit(1)
}

class LocationGetter: NSObject, CLLocationManagerDelegate {
    let manager = CLLocationManager()

    override init() {
        super.init()
        manager.delegate = self
        manager.desiredAccuracy = kCLLocationAccuracyBest
    }

    func start() {
        guard CLLocationManager.locationServicesEnabled() else {
            fail("Location Services is turned off (\(settingsHint)).")
        }
        manager.requestWhenInUseAuthorization()
        manager.startUpdatingLocation()
    }

    func locationManagerDidChangeAuthorization(_ manager: CLLocationManager) {
        switch manager.authorizationStatus {
        case .denied:
            fail("Location permission denied for get-location-mac (\(settingsHint)).")
        case .restricted:
            fail("Location access is restricted on this Mac.")
        default:
            break
        }
    }

    func locationManager(_ manager: CLLocationManager, didUpdateLocations locations: [CLLocation]) {
        guard let location = locations.last else { return }
        let payload: [String: Any] = [
            "latitude": location.coordinate.latitude,
            "longitude": location.coordinate.longitude,
            "accuracy": location.horizontalAccuracy,
            "altitude": location.altitude,
            "timestamp": ISO8601DateFormatter().string(from: location.timestamp)
        ]
        if let json = try? JSONSerialization.data(withJSONObject: payload),
           let jsonString = String(data: json, encoding: .utf8) {
            print(jsonString)
        }
        exit(0)
    }

    func locationManager(_ manager: CLLocationManager, didFailWithError error: Error) {
        // Transient: CoreLocation keeps trying, so wait for a fix or the timeout.
        if (error as? CLError)?.code == .locationUnknown { return }
        fail("Error: \(error.localizedDescription)")
    }
}

let getter = LocationGetter()
getter.start()

RunLoop.main.run(until: Date(timeIntervalSinceNow: 10))
if getter.manager.authorizationStatus == .notDetermined {
    fail("Location permission not granted yet: run `open get-location-mac.app` once and click Allow.")
}
fail("Timed out waiting for a location fix (permission is granted).")
