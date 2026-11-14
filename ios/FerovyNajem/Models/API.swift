import Foundation

/// Mirrors the backend contract (backend/app/api/v1/schemas.py, served at /openapi.json).
/// JSON keys are snake_case; the coders below convert automatically.

enum Status: String, Codable, Hashable, Sendable, Comparable {
    case unknown, green, yellow, red

    private var severity: Int {
        switch self {
        case .unknown: 0
        case .green: 1
        case .yellow: 2
        case .red: 3
        }
    }

    static func < (lhs: Status, rhs: Status) -> Bool { lhs.severity < rhs.severity }
}

// MARK: - Request

struct AddressSuggestion: Codable, Identifiable, Hashable, Sendable {
    let ruianCode: Int
    let label: String
    let lat: Double
    let lon: Double
    var id: Int { ruianCode }
}

enum Disposition: String, CaseIterable, Identifiable, Codable, Hashable, Sendable {
    case oneKK = "1+kk", oneOne = "1+1"
    case twoKK = "2+kk", twoOne = "2+1"
    case threeKK = "3+kk", threeOne = "3+1"
    case fourKK = "4+kk", fourOne = "4+1"
    var id: String { rawValue }
}

/// Extras the MF map prices as surcharges over the reference flat.
struct Features: Codable, Hashable, Sendable {
    var lift = false
    var balcony = false
    var terrace = false
    var furnished = false
    var garage = false
    var newBuild = false
}

enum ScamQuestion: String, CaseIterable, Identifiable, Codable, Hashable, Sendable {
    case depositBeforeViewing = "deposit_before_viewing"
    case videoOnlyViewing = "video_only_viewing"
    case foreignAccount = "foreign_account"
    case ownerAbroad = "owner_abroad"
    case pressureToPay = "pressure_to_pay"
    case unitNumberWithheld = "unit_number_withheld"
    var id: String { rawValue }
}

struct ReportRequest: Encodable, Hashable, Sendable {
    var ruianCode: Int
    var addressLabel: String  // UI only, not sent
    var unitNumber: Int?
    var rentCzk: Int
    var areaM2: Double
    var disposition: Disposition
    var landlordIco: String?
    var features = Features()
    var answers: [ScamQuestion: Bool] = [:]

    private enum CodingKeys: String, CodingKey {
        case ruianCode, unitNumber, rentCzk, areaM2, disposition, landlordIco, features, answers
    }

    func encode(to encoder: Encoder) throws {
        var c = encoder.container(keyedBy: CodingKeys.self)
        try c.encode(ruianCode, forKey: .ruianCode)
        try c.encodeIfPresent(unitNumber, forKey: .unitNumber)
        try c.encode(rentCzk, forKey: .rentCzk)
        try c.encode(areaM2, forKey: .areaM2)
        try c.encode(disposition, forKey: .disposition)
        try c.encodeIfPresent(landlordIco, forKey: .landlordIco)
        try c.encode(features, forKey: .features)
        try c.encode(
            Dictionary(uniqueKeysWithValues: answers.map { ($0.key.rawValue, $0.value) }),
            forKey: .answers
        )
    }
}

// MARK: - Response

struct ReportResponse: Decodable, Hashable, Sendable {
    let overall: Status
    let price: PriceBlock
    let property: PropertyBlock
    let landlord: LandlordBlock?
    let address: AddressBlock
    let scamFlags: ScamBlock
    let disclaimer: String
    let sources: [String]
}

struct PriceBlock: Decodable, Hashable, Sendable {
    enum Verdict: String, Decodable, Sendable {
        case farBelow = "far_below", below, typical, above, farAbove = "far_above"
    }

    let status: Status
    let available: Bool
    let verdict: Verdict?
    let askingPerM2: Double?
    let expectedPerM2: Int?
    let typicalLowPerM2: Int?
    let typicalHighPerM2: Int?
    let referencePerM2: Int?
    let surchargePerM2: Int?
    let rawMin: Int?
    let rawMedian: Int?
    let rawMax: Int?
    let coverage: Int?
    let limitedData: Bool
    let ratio: Double?
    let unitName: String?
    let unitKind: String?
    let sizeCategory: Int?
    let periodEnd: Date?
}

struct Proceeding: Decodable, Hashable, Identifiable, Sendable {
    let type: String
    let number: String
    let state: String?
    let received: Date?
    let scope: String  // unit | building
    let inProgress: Bool
    var id: String { number }
}

struct PropertyBlock: Decodable, Hashable, Sendable {
    let status: Status
    let available: Bool
    let unavailableReason: String?
    let checkLevel: String?  // unit | building
    let buildingFound: Bool?
    let unitFound: Bool?
    let unitUseCode: Int?
    let unitUseName: String?
    let kuName: String?
    let proceedings: [Proceeding]
    let signals: [String]
    let hints: [String]
    let knDeeplink: URL?
    let dataAsOf: Date?
}

struct LandlordBlock: Decodable, Hashable, Sendable {
    let status: Status
    let ico: String
    let found: Bool
    let name: String?
    let naturalPerson: Bool?
    let active: Bool?
    let insolvency: String  // none | active | unknown | not_checked
    let insolvencyStage: String?
    let signals: [String]
}

struct AddressBlock: Decodable, Hashable, Sendable {
    let status: Status
    let floodZone: String?  // none | near | q100 | active; nil = no data
    let distanceM: Int?
    let dataVersion: String?
}

struct ScamBlock: Decodable, Hashable, Sendable {
    let status: Status
    let flags: [String]
}

// MARK: - Coders

enum APICoding {
    static let encoder: JSONEncoder = {
        let e = JSONEncoder()
        e.keyEncodingStrategy = .convertToSnakeCase
        return e
    }()

    static let decoder: JSONDecoder = {
        let d = JSONDecoder()
        d.keyDecodingStrategy = .convertFromSnakeCase
        d.dateDecodingStrategy = .custom { decoder in
            let s = try decoder.singleValueContainer().decode(String.self)
            if let date = parseDate(s) { return date }
            throw DecodingError.dataCorrupted(
                .init(codingPath: decoder.codingPath, debugDescription: "bad date \(s)")
            )
        }
        return d
    }()

    /// Backend sends "2026-09-30" and "2026-11-14T18:20:00[.ffffff]" (Prague local time).
    private static let formats = ["yyyy-MM-dd'T'HH:mm:ss.SSSSSS", "yyyy-MM-dd'T'HH:mm:ss", "yyyy-MM-dd"]

    static func parseDate(_ s: String) -> Date? {
        for f in formats {
            let df = DateFormatter()
            df.locale = Locale(identifier: "en_US_POSIX")
            df.timeZone = TimeZone(identifier: "Europe/Prague")
            df.dateFormat = f
            if let d = df.date(from: s) { return d }
        }
        return nil
    }
}

// MARK: - Input helpers

enum InputParsing {
    /// "24", "1403/24" or "č. 24" → 24
    static func unitNumber(_ text: String) -> Int? {
        let tail = text.split(separator: "/").last.map(String.init) ?? text
        let digits = tail.filter(\.isNumber)
        guard let n = Int(digits), (1...9999).contains(n) else { return nil }
        return n
    }

    /// Czech IČO: 8 digits, mod-11 checksum.
    static func isValidICO(_ ico: String) -> Bool {
        guard ico.count == 8, ico.allSatisfy(\.isNumber) else { return false }
        let d = ico.compactMap { $0.wholeNumberValue }
        let s = zip(d.prefix(7), stride(from: 8, through: 2, by: -1)).reduce(0) { $0 + $1.0 * $1.1 }
        return d[7] == (11 - s % 11) % 10
    }
}
