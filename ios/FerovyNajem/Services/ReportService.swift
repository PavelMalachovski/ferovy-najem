import Foundation

protocol ReportService: Sendable {
    func suggest(_ query: String) async -> [AddressSuggestion]
    func report(for request: ReportRequest) async throws -> Report
}

/// Scoring thresholds. Mirrors backend config (SPEC §6); the real app gets the verdict
/// from the backend and only renders it.
struct ScoringConfig: Sendable {
    var redBelow = 0.70
    var yellowBelow = 0.85
    var yellowAbove = 1.15
    var redAbove = 1.30
    static let `default` = ScoringConfig()
}

/// Offline mock with three fictional Prague addresses. Each one has a property profile so the
/// demo can show every report state. Price is computed from what the user typed.
struct MockReportService: ReportService {
    struct Profile: Sendable {
        let address: AddressSuggestion
        let kuName: String
        let median: Double
        let min: Double
        let max: Double
        let units: [Int: PropertyBlock.UnitUse]
        let unitProceedings: [Int: [Proceeding]]
        let buildingProceedings: [Proceeding]
        let flood: AddressRiskBlock.FloodZone
    }

    static let profiles: [Profile] = [
        Profile(
            address: .init(ruianCode: 900_001, label: "Korunní 1001/12, Praha 2 – Vinohrady"),
            kuName: "Vinohrady", median: 345, min: 250, max: 470,
            units: [1: .flat, 2: .flat, 12: .flat, 14: .flat],
            unitProceedings: [:], buildingProceedings: [], flood: .none
        ),
        Profile(
            address: .init(ruianCode: 900_002, label: "Táboritská 1502/7, Praha 3 – Žižkov"),
            kuName: "Žižkov", median: 320, min: 230, max: 440,
            units: [3: .flat, 5: .studio, 9: .flat],
            unitProceedings: [:], buildingProceedings: [], flood: .none
        ),
        Profile(
            address: .init(ruianCode: 900_003, label: "Sokolovská 1290/41, Praha 8 – Karlín"),
            kuName: "Karlín", median: 390, min: 280, max: 520,
            units: [4: .flat, 8: .flat, 11: .nonResidential],
            unitProceedings: [8: [Proceeding(
                kind: .vklad, number: "V-21873/2026-101", state: "zahájeno",
                received: .daysAgo(9), scope: .unit
            )]],
            buildingProceedings: [Proceeding(
                kind: .zaznam, number: "Z-4410/2026-101", state: nil,
                received: .daysAgo(40), scope: .building
            )],
            flood: .near
        ),
    ]

    var config: ScoringConfig = .default
    var latency: Duration = .milliseconds(900)

    func suggest(_ query: String) async -> [AddressSuggestion] {
        let q = query.folding(options: [.diacriticInsensitive, .caseInsensitive], locale: nil)
        guard !q.isEmpty else { return [] }
        return Self.profiles.map(\.address).filter {
            $0.label.folding(options: [.diacriticInsensitive, .caseInsensitive], locale: nil)
                .contains(q)
        }
    }

    func report(for req: ReportRequest) async throws -> Report {
        try await Task.sleep(for: latency)
        let p = Self.profiles.first { $0.address == req.address } ?? Self.profiles[0]

        // Price
        let perM2 = Double(req.rentCZK) / max(req.areaM2, 1)
        let ratio = perM2 / p.median
        let verdict: PriceBlock.Verdict =
            ratio < config.redBelow ? .farBelow :
            ratio < config.yellowBelow ? .below :
            ratio <= config.yellowAbove ? .typical :
            ratio <= config.redAbove ? .above : .farAbove
        let priceStatus: Status = switch verdict {
        case .farBelow, .farAbove: .red
        case .below, .above: .yellow
        case .typical: .green
        }
        let price = PriceBlock(
            status: priceStatus, verdict: verdict, askingPerM2: perM2, medianPerM2: p.median,
            minPerM2: p.min, maxPerM2: p.max, ratio: ratio, kuName: p.kuName, period: "Q3 2026"
        )

        // Property
        var proceedings = p.buildingProceedings
        var unitFound: Bool?
        var unitUse: PropertyBlock.UnitUse?
        var hints: [PropertyBlock.Hint] = []
        if let n = req.unitNumber {
            unitUse = p.units[n]
            unitFound = unitUse != nil
            proceedings += p.unitProceedings[n] ?? []
        } else {
            hints.append(.askUnitNumber)
        }
        var propStatus: Status = .green
        if unitFound == false || (unitUse.map { $0 != .flat } ?? false) { propStatus = .yellow }
        if !proceedings.isEmpty { propStatus = max(propStatus, .yellow) }
        if proceedings.contains(where: { $0.kind == .vklad && $0.scope == .unit }) { propStatus = .red }
        let property = PropertyBlock(
            status: propStatus, checkLevel: req.unitNumber == nil ? .building : .unit,
            buildingFound: true, unitNumber: req.unitNumber, unitFound: unitFound,
            unitUse: unitUse, proceedings: proceedings, hints: hints,
            lvNumber: req.unitNumber == nil ? nil : 2000 + (req.unitNumber ?? 0)
        )

        // Landlord (ARES/ISIR mock)
        let landlord = req.landlordICO.flatMap { ico -> LandlordBlock? in
            guard !ico.isEmpty else { return nil }
            return LandlordBlock(status: .green, name: "Ukázková Reality s.r.o.", ico: ico,
                                 active: true, insolvency: false)
        }

        // Address risk
        let address = AddressRiskBlock(
            status: p.flood == .none ? .green : .yellow, floodZone: p.flood
        )

        // Scam flags
        var flags = ScamQuestion.allCases
            .filter { req.answers[$0] == true }
            .compactMap { ScamFlag(rawValue: $0.rawValue) }
        if verdict == .farBelow { flags.append(.priceFarBelowMedian) }
        let scamStatus: Status =
            flags.isEmpty ? .green :
            flags == [.unitNumberWithheld] ? .yellow : .red
        let scam = ScamBlock(status: scamStatus, flags: flags)

        // Overall: worst block; "overpriced" alone is information, capped at yellow.
        let priceForOverall: Status = verdict == .farAbove ? .yellow : priceStatus
        let overall = [priceForOverall, property.status, landlord?.status ?? .unknown,
                       address.status, scam.status].max() ?? .unknown

        return Report(
            overall: overall, addressLabel: req.address.label, price: price, property: property,
            landlord: landlord, address: address, scam: scam, dataAsOf: .daysAgo(1)
        )
    }
}

/// Prefilled demo inputs for the three states (DEBUG only in UI).
enum DemoScenario: String, CaseIterable, Identifiable {
    case green, yellow, red
    var id: String { rawValue }

    func makeRequest() -> ReportRequest {
        let a = MockReportService.profiles
        switch self {
        case .green:
            return ReportRequest(address: a[0].address, unitNumber: 12, rentCZK: 21_000,
                                 areaM2: 60, disposition: .twoKK, landlordICO: "12345679")
        case .yellow:
            return ReportRequest(address: a[1].address, unitNumber: nil, rentCZK: 24_000,
                                 areaM2: 60, disposition: .twoKK, landlordICO: nil,
                                 answers: [.unitNumberWithheld: true])
        case .red:
            return ReportRequest(address: a[2].address, unitNumber: 8, rentCZK: 14_000,
                                 areaM2: 55, disposition: .twoOne, landlordICO: nil,
                                 answers: [.depositBeforeViewing: true, .ownerAbroad: true])
        }
    }
}

extension Date {
    static func daysAgo(_ days: Int) -> Date {
        Calendar.current.date(byAdding: .day, value: -days, to: .now) ?? .now
    }
}
