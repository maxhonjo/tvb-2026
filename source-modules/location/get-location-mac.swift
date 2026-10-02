import CoreLocation
import Foundation

class LocationGetter: NSObject, CLLocationManagerDelegate {
    let manager = CLLocationManager()

    override init() {
        super.init()
        manager.delegate = self
        manager.desiredAccuracy = kCLLocationAccuracyBest
    }

    func start() {
        manager.requestWhenInUseAuthorization()
        manager.startUpdatingLocation()
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
        FileHandle.standardError.write("Error: \(error.localizedDescription)\n".data(using: .utf8)!)
        exit(1)
    }
}

let getter = LocationGetter()
getter.start()

RunLoop.main.run(until: Date(timeIntervalSinceNow: 10))
FileHandle.standardError.write("Timed out waiting for location (check Location Services permission).\n".data(using: .utf8)!)
exit(1)
