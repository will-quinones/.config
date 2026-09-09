import CoreGraphics
import Foundation
let windows = CGWindowListCopyWindowInfo(.optionAll, kCGNullWindowID) as? [[String: Any]] ?? []
let ids = windows.compactMap { w -> [Int]? in
    guard let id = w[kCGWindowNumber as String] as? Int,
          let pid = w[kCGWindowOwnerPID as String] as? Int else { return nil }
    return [id, pid]
}
let data = try JSONSerialization.data(withJSONObject: ids)
print(String(decoding: data, as: UTF8.self))
