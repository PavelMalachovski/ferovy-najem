import Foundation

/// Mirrors the backend contract in docs/SPEC.md §6. Field names stay close to the API
/// so the mock can later be swapped for a real HTTP client without touching views.

enum Status: String, Codable, Hashable, Comparable, Sendable {
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

struct AddressSuggestion: Identifiable, Hashable, Sendable {
    let ruianCode: Int
    let label: String
    var id: Int { ruianCode }
}

enum Disposition: String, CaseIterable, Identifiable, Hashable, Sendable {
    case oneKK = "1+kk", oneOne = "1+1"
    case twoKK = "2+kk", twoOne = "2+1"
    case threeKK = "3+kk", threeOne = "3+1"
    case fourKK = "4+kk", fourOne = "4+1"
    var id: String { rawValue }

    /// MF rent map size category (VK 1–4).
    var sizeCategory: Int {
        switch self {
        case .oneKK, .oneOne: 1
        case .twoKK, .twoOne: 2
        case .threeKK, .threeOne: 3
        case .fourKK, .fourOne: 4
        }
    }
}

/// Features priced by the MF map as surcharges over the reference flat
/// (which is unfurnished, without balcony/terrace/garage/lift, older than 5 years).
struct FlatFeatures: Hashable, Sendable {
    var lift = false
    var balcony = false
    var terrace = false
    var furnished = false
    var garage = false
    var newBuild = false
}

/// Questionnaire items. Answer "yes" raises the flag of the same name.
enum ScamQuestion: String, CaseIterable, Identifiable, Hashable, Sendable {
    case depositBeforeViewing
    case videoOnlyViewing
    case foreignAccount
    case ownerAbroad
    case pressureToPay
    case unitNumberWithheld
    var id: String { rawValue }
}

enum ScamFlag: String, Hashable, Sendable {
    case depositBeforeViewing, videoOnlyViewing, foreignAccount, ownerAbroad, pressureToPay
    case unitNumberWithheld
    case priceFarBelowMedian
}

struct ReportRequest: Hashable, Sendable {
    var address: AddressSuggestion
    var unitNumber: Int?
    var rentCZK: Int
    var areaM2: Double
    var disposition: Disposition
    var landlordICO: String?
    var features = FlatFeatures()
    var answers: [ScamQuestion: Bool] = [:]
}

struct Report: Hashable, Sendable {
    var overall: Status
    var addressLabel: String
    var price: PriceBlock
    var property: PropertyBlock
    var landlord: LandlordBlock?
    var address: AddressRiskBlock
    var scam: ScamBlock
    var dataAsOf: Date
}

struct PriceBlock: Hashable, Sendable {
    enum Verdict: Hashable, Sendable { case farBelow, below, typical, above, farAbove }
    var status: Status
    var verdict: Verdict
    var askingPerM2: Double
    /// MF model rent of the reference flat + feature surcharges.
    var referencePerM2: Double
    var surchargePerM2: Double
    var minPerM2: Double
    var maxPerM2: Double
    var ratio: Double
    var kuName: String
    var period: String
}

struct PropertyBlock: Hashable, Sendable {
    enum CheckLevel: Hashable, Sendable { case unit, building }
    enum UnitUse: Hashable, Sendable { case flat, studio, nonResidential }
    enum Hint: Hashable, Sendable { case askUnitNumber, wholeHouse }

    var status: Status
    var checkLevel: CheckLevel
    var buildingFound: Bool
    var unitNumber: Int?
    var unitFound: Bool?
    var unitUse: UnitUse?
    var proceedings: [Proceeding]
    var hints: [Hint]
    var lvNumber: Int?
}

struct Proceeding: Hashable, Identifiable, Sendable {
    enum Kind: Hashable, Sendable { case vklad, zaznam, other }
    enum Scope: Hashable, Sendable { case unit, building }
    var id: String { number }
    var kind: Kind
    var number: String
    var state: String?
    var received: Date
    var scope: Scope
}

struct LandlordBlock: Hashable, Sendable {
    var status: Status
    var name: String
    var ico: String
    var active: Bool
    var insolvency: Bool
}

struct AddressRiskBlock: Hashable, Sendable {
    enum FloodZone: Hashable, Sendable { case none, near, inside }
    var status: Status
    var floodZone: FloodZone
}

struct ScamBlock: Hashable, Sendable {
    var status: Status
    var flags: [ScamFlag]
}
