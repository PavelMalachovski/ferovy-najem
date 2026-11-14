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
                        OverallHeader(report: report)
                        PriceCard(price: report.price, expanded: expandAll)
                        PropertyCard(property: report.property, expanded: expandAll)
                        LandlordCard(landlord: report.landlord, expanded: expandAll)
                        AddressCard(address: report.address, expanded: expandAll)
                        ScamCard(scam: report.scam, expanded: expandAll)
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

    /// DEBUG-only launch flags for screenshots; always false in release builds.
    static func debugFlag(_ key: String) -> Bool {
        #if DEBUG
        UserDefaults.standard.bool(forKey: key)
        #else
        false
        #endif
    }
}

// MARK: - Header

private struct OverallHeader: View {
    let report: Report

    var body: some View {
        VStack(spacing: 12) {
            Image(systemName: report.overall.symbol)
                .font(.system(size: 52, weight: .semibold))
                .foregroundStyle(.white)
                .frame(width: 88, height: 88)
                .background(report.overall.color.gradient, in: Circle())
                .accessibilityHidden(true)
            Text(report.overall.headline)
                .font(.title2.bold())
                .multilineTextAlignment(.center)
            Label(report.addressLabel, systemImage: "mappin.circle")
                .font(.subheadline)
                .foregroundStyle(.secondary)
                .multilineTextAlignment(.center)
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, 24)
        .padding(.horizontal, 16)
        .background(
            report.overall.color.opacity(0.10),
            in: .rect(cornerRadius: 20)
        )
        .padding(.top, 8)
        .accessibilityElement(children: .combine)
    }
}

// MARK: - Blocks

private struct PriceCard: View {
    let price: PriceBlock
    let expanded: Bool

    private var pct: String { abs(price.ratio - 1).formatted(.percent.precision(.fractionLength(0))) }

    private var summary: Text {
        switch price.verdict {
        case .farBelow: Text("\(pct) below the MF median – matches a common scam pattern")
        case .below: Text("\(pct) below the MF median")
        case .typical: Text("Within the usual range for \(price.kuName)")
        case .above, .farAbove: Text("\(pct) above the MF median")
        }
    }

    var body: some View {
        BlockCard("Price", symbol: "chart.bar.fill", status: price.status, summary: summary,
                  expanded: expanded) {
            PriceRangeBar(price: price).padding(.vertical, 4)
            DetailRow("Your rent", Text(verbatim: price.askingPerM2.czkPerM2))
            DetailRow("MF median", Text(verbatim: price.medianPerM2.czkPerM2))
            DetailRow("Cadastral area", Text(verbatim: price.kuName))
            DetailRow("Data period", Text(verbatim: price.period))
            Text("The MF map is based on asking prices and is not authoritative.")
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
    let landlord: LandlordBlock?
    let expanded: Bool

    var body: some View {
        if let l = landlord {
            BlockCard("Landlord", symbol: "briefcase.fill", status: l.status,
                      summary: Text("\(l.name) – active, no insolvency"), expanded: expanded) {
                DetailRow("Company", Text(verbatim: l.name))
                DetailRow("IČO", Text(verbatim: l.ico))
                DetailRow("Status in ARES", Text(l.active ? "Active" : "Inactive"))
                DetailRow("Insolvency register", Text(l.insolvency ? "Found" : "No record"))
            }
        } else {
            BlockCard("Landlord", symbol: "briefcase.fill", status: .unknown,
                      summary: Text("No IČO entered. Private landlord? Use the owner check below."),
                      expanded: false) {
                Text("Enter the company's IČO to check it in ARES and the insolvency register.")
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
            }
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
    let expanded: Bool

    private var summary: Text {
        scam.flags.isEmpty
            ? Text("No typical scam patterns in your answers")
            : Text("\(scam.flags.count) warning signs")
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
        case .priceFarBelowMedian: "Price far below the MF median"
        }
    }
}

#Preview {
    NavigationStack {
        ReportView(service: MockReportService(latency: .zero), request: DemoScenario.red.makeRequest(),
                   expandAll: true) {}
    }
}
