import SwiftUI

struct ReportView: View {
    let service: any ReportService
    let request: ReportRequest
    var expandAll = Self.debugFlag("expand")
    let onNewCheck: () -> Void

    @State private var report: Report?

    var body: some View {
        Group {
            if let report {
                ScrollViewReader { proxy in
                ScrollView {
                    VStack(spacing: 12) {
                        OverallHeader(report: report, blocks: blocks(report))
                        NextStepsCard(report: report)
                        Text("Details · most serious first")
                            .font(.footnote.weight(.semibold))
                            .foregroundStyle(.secondary)
                            .textCase(.uppercase)
                            .frame(maxWidth: .infinity, alignment: .leading)
                            .padding(.horizontal, 4)
                            .padding(.top, 8)
                        ForEach(blocks(report)) { block in
                            card(block, report)
                        }
                        ShareLink(item: shareText(report)) {
                            Label("Share result", systemImage: "square.and.arrow.up")
                                .frame(maxWidth: .infinity)
                        }
                        .buttonStyle(.bordered)
                        .controlSize(.large)
                        .padding(.top, 4)
                        OwnerCheckSection()
                        DisclaimerFooter(dataAsOf: report.dataAsOf).id("bottom")
                    }
                    .padding(.horizontal)
                    .padding(.bottom, 24)
                }
                .background(Color(.systemGroupedBackground))
                .onAppear {
                    #if DEBUG
                    if UserDefaults.standard.string(forKey: "scroll") == "bottom" {
                        proxy.scrollTo("bottom", anchor: .bottom)
                    }
                    #endif
                }
                }
            } else {
                VStack(spacing: 16) {
                    ProgressView().controlSize(.large)
                    Text("Checking the cadastre, rent map and registers…")
                        .foregroundStyle(.secondary)
                        .multilineTextAlignment(.center)
                }
                .padding()
                .frame(maxWidth: .infinity, maxHeight: .infinity)
                .background(Color(.systemGroupedBackground))
            }
        }
        .navigationTitle("Report")
        .navigationBarTitleDisplayMode(.inline)
        .toolbar {
            ToolbarItem(placement: .topBarTrailing) {
                Button("New check", action: onNewCheck)
            }
        }
        .task { report = try? await service.report(for: request) }
    }

    /// Blocks sorted by severity (stable: same status keeps the default order).
    /// The landlord block is shown only when an IČO was entered.
    private func blocks(_ report: Report) -> [Block] {
        var all: [Block] = [.init(kind: .price, status: report.price.status),
                            .init(kind: .property, status: report.property.status)]
        if let l = report.landlord { all.append(.init(kind: .landlord, status: l.status)) }
        all.append(.init(kind: .address, status: report.address.status))
        all.append(.init(kind: .scam, status: report.scam.status))
        return all.enumerated()
            .sorted { $0.element.status != $1.element.status ? $0.element.status > $1.element.status : $0.offset < $1.offset }
            .map(\.element)
    }

    @ViewBuilder
    private func card(_ block: Block, _ report: Report) -> some View {
        let expanded = expandAll || block.status == .red
        switch block.kind {
        case .price: PriceCard(price: report.price, areaM2: request.areaM2, expanded: expanded)
        case .property: PropertyCard(property: report.property, expanded: expanded)
        case .landlord: if let l = report.landlord { LandlordCard(landlord: l, expanded: expanded) }
        case .address: AddressCard(address: report.address, expanded: expanded)
        case .scam:
            ScamCard(scam: report.scam, unanswered: ScamQuestion.allCases.count - request.answers.count,
                     expanded: expanded)
        }
    }

    private func shareText(_ report: Report) -> String {
        [String(localized: report.overall.headline),
         report.addressLabel,
         String(localized: "Checked with Férový nájem. Indicative information, not a legal assessment.")]
            .joined(separator: "\n")
    }

    /// DEBUG-only launch flags for screenshots; always false in release builds.
    static func debugFlag(_ key: String) -> Bool {
        #if DEBUG
        UserDefaults.standard.bool(forKey: key)
        #else
        false
        #endif
    }
}

private struct Block: Identifiable {
    enum Kind { case price, property, landlord, address, scam }
    let kind: Kind
    let status: Status
    var id: Kind { kind }
}

// MARK: - Header + next steps

private struct OverallHeader: View {
    let report: Report
    let blocks: [Block]

    private var serious: Int { blocks.filter { $0.status == .red }.count }
    private var toCheck: Int { blocks.filter { $0.status == .yellow }.count }

    var body: some View {
        VStack(spacing: 10) {
            Image(systemName: report.overall.symbol)
                .font(.system(size: 40, weight: .semibold))
                .foregroundStyle(.white)
                .frame(width: 72, height: 72)
                .background(report.overall.color.gradient, in: Circle())
                .accessibilityHidden(true)
            Text(report.overall.headline)
                .font(.title2.bold())
                .multilineTextAlignment(.center)
            Text(verbatim: report.addressLabel)
                .font(.subheadline)
                .foregroundStyle(.secondary)
                .multilineTextAlignment(.center)
            if serious + toCheck > 0 {
                HStack(spacing: 8) {
                    if serious > 0 { CountBadge(status: .red, text: Text("\(serious) serious")) }
                    if toCheck > 0 { CountBadge(status: .yellow, text: Text("\(toCheck) to check")) }
                }
                .padding(.top, 2)
            }
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, 22)
        .padding(.horizontal, 16)
        .background(report.overall.color.opacity(0.10), in: .rect(cornerRadius: 20))
        .padding(.top, 8)
        .accessibilityElement(children: .combine)
    }
}

private struct CountBadge: View {
    let status: Status
    let text: Text

    var body: some View {
        Label { text } icon: { Image(systemName: status.symbol) }
            .font(.subheadline.weight(.semibold))
            .foregroundStyle(status.color)
            .padding(.horizontal, 12)
            .padding(.vertical, 6)
            .background(Color(.secondarySystemGroupedBackground), in: Capsule())
    }
}

/// The answer to "what do I do now", right under the verdict.
private struct NextStepsCard: View {
    let report: Report

    private var steps: [Text] {
        var s = [
            Text("**Don't pay a deposit** until you have seen the flat in person and signed the contract."),
            Text("**Check the owner** in the cadastre with your eID and compare the name with the landlord."),
        ]
        if let p = report.property.proceedings.first(where: { $0.kind == .vklad && $0.scope == .unit }) {
            s.append(Text("**Ask** what ownership change is being registered on the unit (\(p.number))."))
        } else if report.property.hints.contains(.askUnitNumber) || report.property.unitFound == false {
            s.append(Text("**Ask** the landlord for the unit number or the LV number."))
        }
        return s
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            Text("What to do now").font(.title3.bold())
            ForEach(Array(steps.enumerated()), id: \.offset) { i, step in
                HStack(alignment: .top, spacing: 12) {
                    Text(verbatim: "\(i + 1)")
                        .font(.subheadline.bold())
                        .foregroundStyle(.white)
                        .frame(width: 26, height: 26)
                        .background(Color.accentColor, in: Circle())
                        .accessibilityHidden(true)
                    step.fixedSize(horizontal: false, vertical: true)
                }
            }
            Link(destination: URL(string: "https://nahlizenidokn.cuzk.gov.cz")!) {
                Label("Check the owner in the cadastre", systemImage: "arrow.up.right")
                    .frame(maxWidth: .infinity)
            }
            .buttonStyle(.borderedProminent)
            .controlSize(.large)
        }
        .card()
    }
}

// MARK: - Blocks

private struct PriceCard: View {
    let price: PriceBlock
    let areaM2: Double
    let expanded: Bool
    var config: ScoringConfig = .default

    private var pct: String { abs(price.ratio - 1).formatted(.percent.precision(.fractionLength(0))) }
    private var monthly: Double { price.askingPerM2 * areaM2 }
    private var usualLow: Double { price.referencePerM2 * config.yellowBelow * areaM2 }
    private var usualHigh: Double { price.referencePerM2 * config.yellowAbove * areaM2 }

    private var summary: Text {
        switch price.verdict {
        case .farBelow: Text("\(pct) below the MF reference rent – matches a common scam pattern")
        case .below: Text("\(pct) below the MF reference rent")
        case .typical: Text("Within the usual range for \(price.kuName)")
        case .above, .farAbove: Text("\(pct) above the MF reference rent")
        }
    }

    var body: some View {
        BlockCard("Price", symbol: "chart.bar.fill", status: price.status, summary: summary,
                  expanded: expanded) {
            HStack(alignment: .top, spacing: 12) {
                VStack(alignment: .leading, spacing: 2) {
                    Text("Your rent").font(.caption).foregroundStyle(.secondary)
                    Text(verbatim: monthly.czk)
                        .font(.title2.bold())
                        .foregroundStyle(price.status == .green ? Color.primary : price.status.color)
                    Text(verbatim: price.askingPerM2.czkPerM2).font(.caption).foregroundStyle(.secondary)
                }
                .frame(maxWidth: .infinity, alignment: .leading)
                VStack(alignment: .leading, spacing: 2) {
                    Text("Usual (MF)").font(.caption).foregroundStyle(.secondary)
                    Text(verbatim: "\(usualLow.hundreds)–\(usualHigh.hundreds)").font(.title2.bold())
                    Text("Kč per month").font(.caption).foregroundStyle(.secondary)
                }
                .frame(maxWidth: .infinity, alignment: .leading)
            }
            .minimumScaleFactor(0.7)
            PriceRangeBar(price: price)
            DetailRow("MF reference rent", Text(verbatim: (price.referencePerM2 * areaM2).czk))
            if price.surchargePerM2 > 0 {
                DetailRow("incl. features", Text(verbatim: "+" + (price.surchargePerM2 * areaM2).czk))
            }
            DetailRow("Cadastral area", Text(verbatim: price.kuName))
            DetailRow("Data period", Text(verbatim: price.period))
            Text("The MF map is based on asking prices and is not authoritative. Rent without service charges.")
                .font(.footnote)
                .foregroundStyle(.secondary)
        }
    }
}

private struct PropertyCard: View {
    let property: PropertyBlock
    let expanded: Bool

    private var unitLabel: String { property.unitNumber.map(String.init) ?? "" }

    private var summary: Text {
        if property.proceedings.contains(where: { $0.kind == .vklad && $0.scope == .unit }) {
            return Text("A change of ownership or lien is being registered on this unit")
        }
        if property.checkLevel == .building {
            return Text("Building found. Checked at building level only.")
        }
        if property.unitFound == false {
            return Text("Unit \(unitLabel) was not found in this building")
        }
        switch property.unitUse {
        case .studio: return Text("Unit \(unitLabel) is registered as a studio (ateliér), not a flat")
        case .nonResidential: return Text("Unit \(unitLabel) is registered as non-residential space")
        default: break
        }
        if !property.proceedings.isEmpty {
            return Text("Unit \(unitLabel) is a flat; the building has a pending proceeding")
        }
        return Text("Unit \(unitLabel) exists and is registered as a flat")
    }

    var body: some View {
        BlockCard("Property", symbol: "building.2.fill", status: property.status,
                  summary: summary, expanded: expanded) {
            DetailRow("Building", Text(property.buildingFound ? "Found" : "Not found"))
            if property.checkLevel == .unit {
                DetailRow("Unit", Text(property.unitFound == true ? "\(unitLabel) – found" : "\(unitLabel) – not found"))
                if let use = property.unitUse { DetailRow("Registered use", Text(use.label)) }
                if let lv = property.lvNumber { DetailRow("LV", Text(verbatim: String(lv))) }
            }
            if property.proceedings.isEmpty {
                DetailRow("Pending proceedings", Text("None"))
            } else {
                Text("Pending proceedings").font(.subheadline.weight(.semibold))
                ForEach(property.proceedings) { ProceedingRow(proceeding: $0) }
            }
            ForEach(property.hints, id: \.self) { hint in
                switch hint {
                case .askUnitNumber:
                    Callout(symbol: "lightbulb.fill",
                            text: Text("Ask the landlord for the unit number (číslo jednotky) or the LV number. A genuine owner can give it right away."))
                case .wholeHouse:
                    Callout(symbol: "info.circle.fill",
                            text: Text("This building has no separate units, so only the building was checked."))
                }
            }
        }
    }
}

private struct ProceedingRow: View {
    let proceeding: Proceeding

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack {
                Text(verbatim: proceeding.number).font(.subheadline.monospaced())
                Spacer()
                Text(proceeding.scope == .unit ? "on the unit" : "on the building")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
            Text(proceeding.kind.explanation).font(.subheadline)
            Text("Received \(proceeding.received.formatted(date: .abbreviated, time: .omitted))")
                .font(.caption)
                .foregroundStyle(.secondary)
        }
        .padding(10)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Color(.tertiarySystemFill), in: .rect(cornerRadius: 10))
    }
}

private struct LandlordCard: View {
    let landlord: LandlordBlock
    let expanded: Bool

    var body: some View {
        BlockCard("Landlord", symbol: "briefcase.fill", status: landlord.status,
                  summary: Text("\(landlord.name) – active, no insolvency"), expanded: expanded) {
            DetailRow("Company", Text(verbatim: landlord.name))
            DetailRow("IČO", Text(verbatim: landlord.ico))
            DetailRow("Status in ARES", Text(landlord.active ? "Active" : "Inactive"))
            DetailRow("Insolvency register", Text(landlord.insolvency ? "Found" : "No record"))
        }
    }
}

private struct AddressCard: View {
    let address: AddressRiskBlock
    let expanded: Bool

    private var summary: Text {
        switch address.floodZone {
        case .none: Text("Not in a mapped flood zone")
        case .near: Text("Near a flood zone (Q100)")
        case .inside: Text("Inside a flood zone (Q100)")
        }
    }

    var body: some View {
        BlockCard("Address", symbol: "drop.fill", status: address.status, summary: summary,
                  expanded: expanded) {
            Text("Q100 is the area flooded on average once in 100 years. Ask about the flood history and insurance.")
                .font(.subheadline)
                .foregroundStyle(.secondary)
        }
    }
}

private struct ScamCard: View {
    let scam: ScamBlock
    let unanswered: Int
    let expanded: Bool

    private var summary: Text {
        if !scam.flags.isEmpty { return Text("\(scam.flags.count) warning signs") }
        if scam.status == .unknown { return Text("You skipped the questions") }
        return Text("No typical scam patterns in your answers")
    }

    var body: some View {
        BlockCard("Scam patterns", symbol: "exclamationmark.bubble.fill", status: scam.status,
                  summary: summary, expanded: expanded) {
            if scam.flags.isEmpty {
                Text("Still: never pay a deposit before you have seen the flat and the contract.")
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
            } else {
                ForEach(scam.flags, id: \.self) { flag in
                    Label {
                        Text(flag.text)
                    } icon: {
                        Image(systemName: "exclamationmark.circle.fill")
                            .foregroundStyle(flag == .unitNumberWithheld ? Status.yellow.color : Status.red.color)
                    }
                    .font(.subheadline)
                }
                Text("These patterns are common in rental scams. They don't prove anything about a specific person.")
                    .font(.footnote)
                    .foregroundStyle(.secondary)
            }
            if unanswered > 0 && scam.status != .unknown {
                Text("Questions without an answer: \(unanswered)")
                    .font(.footnote)
                    .foregroundStyle(.secondary)
            }
        }
    }
}

// MARK: - Owner check + footer

private struct OwnerCheckSection: View {
    private let steps: [LocalizedStringKey] = [
        "Open Nahlížení do katastru and sign in with your eID (e.g. bank identity).",
        "Find the flat by address and unit number.",
        "Compare the owner's name with the person you are talking to.",
        "Different name? Ask for a power of attorney or the lease between the owner and the landlord.",
    ]

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Label("Check the owner yourself", systemImage: "person.text.rectangle.fill")
                .font(.headline)
            ForEach(Array(steps.enumerated()), id: \.offset) { i, step in
                HStack(alignment: .top, spacing: 10) {
                    Text(verbatim: "\(i + 1)")
                        .font(.caption.bold())
                        .foregroundStyle(.white)
                        .frame(width: 22, height: 22)
                        .background(Color.accentColor, in: Circle())
                    Text(step).font(.subheadline).fixedSize(horizontal: false, vertical: true)
                }
            }
            Link(destination: URL(string: "https://nahlizenidokn.cuzk.gov.cz")!) {
                Label("Open Nahlížení do katastru", systemImage: "arrow.up.right.square")
                    .frame(maxWidth: .infinity)
            }
            .buttonStyle(.bordered)
            .controlSize(.large)
        }
        .padding(16)
        .background(Color(.secondarySystemGroupedBackground), in: .rect(cornerRadius: 16))
    }
}

private struct DisclaimerFooter: View {
    let dataAsOf: Date

    var body: some View {
        VStack(spacing: 6) {
            Text("Indicative information, not a legal assessment.")
                .font(.footnote.weight(.semibold))
            Text("Data as of \(dataAsOf.formatted(date: .abbreviated, time: .omitted)). Sources: ČÚZK (CC BY 4.0), MF ČR, ARES, ISIR.")
                .font(.footnote)
        }
        .foregroundStyle(.secondary)
        .multilineTextAlignment(.center)
        .padding(.top, 8)
    }
}

// MARK: - Texts for codes

extension PropertyBlock.UnitUse {
    var label: LocalizedStringKey {
        switch self {
        case .flat: "Flat (byt)"
        case .studio: "Studio (ateliér)"
        case .nonResidential: "Non-residential space"
        }
    }
}

extension Proceeding.Kind {
    var explanation: LocalizedStringKey {
        switch self {
        case .vklad: "Vklad – a change of ownership or a lien is being registered"
        case .zaznam: "Záznam – a right is being recorded based on an official decision"
        case .other: "Other proceeding"
        }
    }
}

extension ScamFlag {
    var text: LocalizedStringKey {
        switch self {
        case .depositBeforeViewing: "Deposit requested before viewing"
        case .videoOnlyViewing: "Viewing only by video or photos"
        case .foreignAccount: "Payment to a foreign bank account"
        case .ownerAbroad: "Landlord says they are abroad"
        case .pressureToPay: "Pressure to pay immediately"
        case .unitNumberWithheld: "Unit number or LV not provided"
        case .priceFarBelowMedian: "Price far below the MF reference rent"
        }
    }
}

#Preview {
    NavigationStack {
        ReportView(service: MockReportService(latency: .zero), request: DemoScenario.red.makeRequest(),
                   expandAll: true) {}
    }
}
