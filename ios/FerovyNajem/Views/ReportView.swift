import SwiftUI

struct ReportView: View {
    let service: any ReportService
    let request: ReportRequest
    var expandAll = Self.debugFlag("expand")
    let onNewCheck: () -> Void

    private enum Phase { case loading, loaded(ReportResponse), failed(APIError) }
    @State private var phase: Phase = .loading
    @State private var attempt = 0

    var body: some View {
        Group {
            switch phase {
            case .loading:
                VStack(spacing: 16) {
                    ProgressView().controlSize(.large)
                    Text("Checking the cadastre, rent map and registers…")
                        .foregroundStyle(.secondary)
                        .multilineTextAlignment(.center)
                }
                .padding()
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            case .failed(let error):
                ErrorView(error: error) { attempt += 1 }
            case .loaded(let report):
                content(report)
            }
        }
        .background(Color(.systemGroupedBackground))
        .navigationTitle("Report")
        .navigationBarTitleDisplayMode(.inline)
        .toolbar {
            ToolbarItem(placement: .topBarTrailing) {
                Button("New check", action: onNewCheck)
            }
        }
        .task(id: attempt) {
            phase = .loading
            do {
                phase = .loaded(try await service.report(request))
            } catch let e as APIError {
                phase = .failed(e)
            } catch is CancellationError {
            } catch {
                phase = .failed(.badResponse)
            }
        }
    }

    private func content(_ report: ReportResponse) -> some View {
        ScrollViewReader { proxy in
            ScrollView {
                VStack(spacing: 12) {
                    OverallHeader(status: report.overall, address: request.addressLabel, blocks: blocks(report))
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
                    OwnerCheckSection(link: report.property.knDeeplink)
                    DisclaimerFooter(report: report).id("bottom")
                }
                .padding(.horizontal)
                .padding(.bottom, 24)
            }
            .onAppear {
                #if DEBUG
                if UserDefaults.standard.string(forKey: "scroll") == "bottom" {
                    proxy.scrollTo("bottom", anchor: .bottom)
                }
                #endif
            }
        }
    }

    /// Blocks sorted by severity (stable: same status keeps the default order).
    /// The landlord block is shown only when an IČO was entered.
    private func blocks(_ report: ReportResponse) -> [Block] {
        var all: [Block] = [.init(kind: .price, status: report.price.status),
                            .init(kind: .property, status: report.property.status)]
        if let l = report.landlord { all.append(.init(kind: .landlord, status: l.status)) }
        all.append(.init(kind: .address, status: report.address.status))
        all.append(.init(kind: .scam, status: report.scamFlags.status))
        return all.enumerated()
            .sorted { $0.element.status != $1.element.status ? $0.element.status > $1.element.status : $0.offset < $1.offset }
            .map(\.element)
    }

    @ViewBuilder
    private func card(_ block: Block, _ report: ReportResponse) -> some View {
        let expanded = expandAll || block.status == .red
        switch block.kind {
        case .price: PriceCard(price: report.price, rentCzk: request.rentCzk, areaM2: request.areaM2, expanded: expanded)
        case .property: PropertyCard(property: report.property, unit: request.unitNumber, expanded: expanded)
        case .landlord: if let l = report.landlord { LandlordCard(landlord: l, expanded: expanded) }
        case .address: AddressCard(address: report.address, expanded: expanded)
        case .scam:
            ScamCard(scam: report.scamFlags, unanswered: ScamQuestion.allCases.count - request.answers.count,
                     expanded: expanded)
        }
    }

    private func shareText(_ report: ReportResponse) -> String {
        [String(localized: report.overall.headline),
         request.addressLabel,
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

private struct ErrorView: View {
    let error: APIError
    let retry: () -> Void

    var body: some View {
        VStack(spacing: 16) {
            Image(systemName: error == .rateLimited ? "hourglass" : "wifi.exclamationmark")
                .font(.system(size: 44))
                .foregroundStyle(.secondary)
            Text(title).font(.title3.bold()).multilineTextAlignment(.center)
            Text(message).foregroundStyle(.secondary).multilineTextAlignment(.center)
            if error != .rateLimited {
                Button("Try again", action: retry).buttonStyle(.borderedProminent).controlSize(.large)
            }
        }
        .padding(32)
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }

    private var title: LocalizedStringKey {
        switch error {
        case .offline: "Can't reach the server"
        case .rateLimited: "Too many checks"
        case .server, .badResponse: "Something went wrong"
        }
    }

    private var message: LocalizedStringKey {
        switch error {
        case .offline: "Check your internet connection and try again."
        case .rateLimited: "You've made a lot of checks in a short time. Please try again in an hour."
        case .server, .badResponse: "The check couldn't be completed. Please try again in a moment."
        }
    }
}

// MARK: - Header + next steps

private struct OverallHeader: View {
    let status: Status
    let address: String
    let blocks: [Block]

    private var serious: Int { blocks.filter { $0.status == .red }.count }
    private var toCheck: Int { blocks.filter { $0.status == .yellow }.count }

    var body: some View {
        VStack(spacing: 10) {
            Image(systemName: status.symbol)
                .font(.system(size: 40, weight: .semibold))
                .foregroundStyle(.white)
                .frame(width: 72, height: 72)
                .background(status.color.gradient, in: Circle())
                .accessibilityHidden(true)
            Text(status.headline)
                .font(.title2.bold())
                .multilineTextAlignment(.center)
            Text(verbatim: address)
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
        .background(status.color.opacity(0.10), in: .rect(cornerRadius: 20))
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
    let report: ReportResponse

    private var steps: [Text] {
        var s = [
            Text("**Don't pay a deposit** until you have seen the flat in person and signed the contract."),
            Text("**Check the owner** in the cadastre with your eID and compare the name with the landlord."),
        ]
        let p = report.property
        if let r = p.proceedings.first(where: { $0.type == "V" && $0.scope == "unit" && $0.inProgress }) {
            s.append(Text("**Ask** what ownership change is being registered on the unit (\(r.number))."))
        } else if p.hints.contains("ask_unit_number") || p.unitFound == false {
            s.append(Text("**Ask** the landlord for the unit number or the LV number."))
        }
        if report.landlord?.insolvency == "active" {
            s.append(Text("**Don't sign** with a company in insolvency without legal advice."))
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
            Link(destination: report.property.knDeeplink ?? URL(string: "https://nahlizenidokn.cuzk.gov.cz")!) {
                Label("Check the owner in the cadastre", systemImage: "arrow.up.right")
                    .frame(maxWidth: .infinity)
            }
            .buttonStyle(.borderedProminent)
            .controlSize(.large)
        }
        .card()
    }
}

// MARK: - Price

private struct PriceCard: View {
    let price: PriceBlock
    let rentCzk: Int  // shown as entered; per-m² values from the API are rounded
    let areaM2: Double
    let expanded: Bool

    private var pct: String { abs((price.ratio ?? 1) - 1).formatted(.percent.precision(.fractionLength(0))) }

    private var summary: Text {
        guard price.available, let verdict = price.verdict else {
            return Text("Price comparison isn't available for this address.")
        }
        switch verdict {
        case .farBelow:
            return price.limitedData
                ? Text("\(pct) below the MF reference rent")
                : Text("\(pct) below the MF reference rent – matches a common scam pattern")
        case .below: return Text("\(pct) below the MF reference rent")
        case .typical: return Text("Within the usual range for \(price.unitName ?? "")")
        case .above, .farAbove: return Text("\(pct) above the MF reference rent")
        }
    }

    var body: some View {
        BlockCard("Price", symbol: "chart.bar.fill", status: price.status, summary: summary,
                  expanded: expanded) {
            if let asking = price.askingPerM2, let expected = price.expectedPerM2,
               let low = price.typicalLowPerM2, let high = price.typicalHighPerM2 {
                HStack(alignment: .top, spacing: 12) {
                    VStack(alignment: .leading, spacing: 2) {
                        Text("Your rent").font(.caption).foregroundStyle(.secondary)
                        Text(verbatim: Double(rentCzk).czk)
                            .font(.title2.bold())
                            .foregroundStyle(price.status == .green ? Color.primary : price.status.color)
                        Text(verbatim: asking.czkPerM2).font(.caption).foregroundStyle(.secondary)
                    }
                    .frame(maxWidth: .infinity, alignment: .leading)
                    VStack(alignment: .leading, spacing: 2) {
                        Text("Usual (MF)").font(.caption).foregroundStyle(.secondary)
                        Text(verbatim: "\((Double(low) * areaM2).hundreds)–\((Double(high) * areaM2).hundreds)")
                            .font(.title2.bold())
                        Text("Kč per month").font(.caption).foregroundStyle(.secondary)
                    }
                    .frame(maxWidth: .infinity, alignment: .leading)
                }
                .minimumScaleFactor(0.7)
                PriceRangeBar(asking: asking, expected: Double(expected), typicalLow: Double(low),
                              typicalHigh: Double(high), status: price.status)
                DetailRow("MF reference rent", Text(verbatim: (Double(expected) * areaM2).czk))
                if let s = price.surchargePerM2, s > 0 {
                    DetailRow("incl. features", Text(verbatim: "+" + (Double(s) * areaM2).czk))
                }
                if let mn = price.rawMin, let mx = price.rawMax {
                    DetailRow("Asking prices in the area", Text(verbatim: "\(Double(mn).czk) – \(mx.czkPerM2)"))
                }
                if let name = price.unitName {
                    DetailRow(price.unitKind == "obec" ? "Municipality" : "Cadastral area", Text(verbatim: name))
                }
                if let end = price.periodEnd {
                    DetailRow("Data up to", Text(end.formatted(date: .abbreviated, time: .omitted)))
                }
                if price.limitedData {
                    Callout(symbol: "exclamationmark.circle",
                            text: Text("Limited data in this area – the comparison is less reliable."),
                            tint: .orange)
                }
            }
            Text("The MF map is based on asking prices and is not authoritative. Rent without service charges.")
                .font(.footnote)
                .foregroundStyle(.secondary)
        }
    }
}

// MARK: - Property

private struct PropertyCard: View {
    let property: PropertyBlock
    let unit: Int?
    let expanded: Bool

    private var unitLabel: String { unit.map(String.init) ?? "" }
    private var useName: String { property.unitUseName ?? "" }

    private var summary: Text {
        if !property.available { return Text("The cadastre is temporarily unavailable. Try again later.") }
        if property.buildingFound == false { return Text("No building found in the cadastre for this address") }
        let s = Set(property.signals)
        if s.contains("ownership_change_in_progress_unit") {
            return Text("A change of ownership or lien is being registered on this unit")
        }
        if s.contains("unit_not_found") { return Text("Unit \(unitLabel) was not found in this building") }
        if s.contains("unit_not_registered_as_flat") {
            return Text("Unit \(unitLabel) is registered as \(useName), not as a flat")
        }
        if s.contains("unit_unfinished") { return Text("Unit \(unitLabel) is registered as unfinished") }
        if s.contains("unit_is_group") {
            return Text("Unit \(unitLabel) is registered as a group of units, not a single flat")
        }
        if s.contains("proceeding_in_progress") { return Text("A proceeding is in progress in the cadastre") }
        if property.checkLevel == "building" { return Text("Building found. Checked at building level only.") }
        return Text("Unit \(unitLabel) exists and is registered as a flat")
    }

    var body: some View {
        BlockCard("Property", symbol: "building.2.fill", status: property.status,
                  summary: summary, expanded: expanded) {
            if property.available, property.buildingFound == true {
                DetailRow("Building", Text("Found"))
                if let ku = property.kuName { DetailRow("Cadastral area", Text(verbatim: ku)) }
                if property.checkLevel == "unit" {
                    DetailRow("Unit", Text(property.unitFound == true ? "\(unitLabel) – found" : "\(unitLabel) – not found"))
                    if let use = property.unitUseName { DetailRow("Registered use", Text(verbatim: use)) }
                }
                if property.proceedings.isEmpty {
                    DetailRow("Pending proceedings", Text("None"))
                } else {
                    Text("Proceedings").font(.subheadline.weight(.semibold))
                    ForEach(property.proceedings) { ProceedingRow(proceeding: $0) }
                }
                if let asOf = property.dataAsOf {
                    DetailRow("Cadastre data as of", Text(asOf.formatted(date: .abbreviated, time: .shortened)))
                }
            }
            ForEach(property.hints, id: \.self) { hint in
                switch hint {
                case "ask_unit_number":
                    Callout(symbol: "lightbulb.fill",
                            text: Text("Ask the landlord for the unit number (číslo jednotky) or the LV number. A genuine owner can give it right away."))
                case "whole_house":
                    Callout(symbol: "info.circle.fill",
                            text: Text("This building has no separate units, so only the building was checked."))
                default:
                    EmptyView()
                }
            }
        }
    }
}

private struct ProceedingRow: View {
    let proceeding: Proceeding

    private var explanation: LocalizedStringKey {
        switch proceeding.type {
        case "V": "Vklad – a change of ownership or a lien is being registered"
        case "Z": "Záznam – a right is being recorded based on an official decision"
        case "PGP": "Confirmation of a geometric plan"
        default: "Other proceeding"
        }
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack {
                Text(verbatim: proceeding.number).font(.subheadline.monospaced())
                Spacer()
                Text(proceeding.scope == "unit" ? "on the unit" : "on the building")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
            Text(explanation).font(.subheadline)
            Text(proceeding.inProgress ? "In progress" : "Finished")
                .font(.caption.weight(.semibold))
                .foregroundStyle(proceeding.inProgress ? Color.orange : Color.secondary)
            if let received = proceeding.received {
                Text("Received \(received.formatted(date: .abbreviated, time: .omitted))")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
        }
        .padding(10)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Color(.tertiarySystemFill), in: .rect(cornerRadius: 10))
    }
}

// MARK: - Landlord

private struct LandlordCard: View {
    let landlord: LandlordBlock
    let expanded: Bool

    private var summary: Text {
        let l = landlord
        if l.signals.contains("ico_invalid") { return Text("This IČO is not valid") }
        if l.signals.contains("ico_not_found") { return Text("IČO \(l.ico) was not found in ARES") }
        if l.status == .unknown { return Text("The registers are temporarily unavailable") }
        if l.insolvency == "active" { return Text("Insolvency proceeding in progress (\(l.insolvencyStage ?? "–"))") }
        if l.active != true { return Text("The company is not active") }
        if l.naturalPerson == true { return Text("Registered sole trader (OSVČ), active") }
        return Text("\(l.name ?? l.ico) – active, no insolvency")
    }

    private var insolvency: Text {
        switch landlord.insolvency {
        case "none": Text("No ongoing proceeding")
        case "active": Text("In progress: \(landlord.insolvencyStage ?? "–")")
        case "not_checked": Text("Not checked for sole traders")
        default: Text("Unavailable")
        }
    }

    var body: some View {
        BlockCard("Landlord", symbol: "briefcase.fill", status: landlord.status, summary: summary,
                  expanded: expanded) {
            if let name = landlord.name { DetailRow("Company", Text(verbatim: name)) }
            DetailRow("IČO", Text(verbatim: landlord.ico))
            if landlord.found {
                DetailRow("Status in ARES", Text(landlord.active == true ? "Active" : "Not active"))
                DetailRow("Insolvency register", insolvency)
            }
        }
    }
}

// MARK: - Address

private struct AddressCard: View {
    let address: AddressBlock
    let expanded: Bool

    private var summary: Text {
        switch address.floodZone {
        case "none": Text("Not in a mapped flood zone")
        case "near": Text("\(address.distanceM ?? 0) m from a flood zone (Q100)")
        case "q100": Text("Inside a flood zone (Q100)")
        case "active": Text("Inside the active flood zone")
        default: Text("Flood data isn't available")
        }
    }

    var body: some View {
        BlockCard("Address", symbol: "drop.fill", status: address.status, summary: summary,
                  expanded: expanded) {
            Text("Q100 is the area flooded on average once in 100 years. Ask about the flood history and insurance.")
                .font(.subheadline)
                .foregroundStyle(.secondary)
            Text("Zones are indicative; the binding extent is set by the water authority.")
                .font(.footnote)
                .foregroundStyle(.secondary)
        }
    }
}

// MARK: - Scam

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
                        Text(Self.text(flag))
                    } icon: {
                        Image(systemName: "exclamationmark.circle.fill")
                            .foregroundStyle(flag == "unit_number_withheld" ? Status.yellow.color : Status.red.color)
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

    static func text(_ flag: String) -> LocalizedStringKey {
        switch flag {
        case "deposit_before_viewing": "Deposit requested before viewing"
        case "video_only_viewing": "Viewing only by video or photos"
        case "foreign_account": "Payment to a foreign bank account"
        case "owner_abroad": "Landlord says they are abroad"
        case "pressure_to_pay": "Pressure to pay immediately"
        case "unit_number_withheld": "Unit number or LV not provided"
        case "price_far_below_reference": "Price far below the MF reference rent"
        default: "Other warning sign"
        }
    }
}

// MARK: - Owner check + footer

private struct OwnerCheckSection: View {
    let link: URL?

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
            Link(destination: link ?? URL(string: "https://nahlizenidokn.cuzk.gov.cz")!) {
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
    let report: ReportResponse

    var body: some View {
        VStack(spacing: 6) {
            Text(verbatim: report.disclaimer).font(.footnote.weight(.semibold))
            Text(verbatim: report.sources.joined(separator: " · ")).font(.footnote)
        }
        .foregroundStyle(.secondary)
        .multilineTextAlignment(.center)
        .padding(.top, 8)
    }
}

#Preview {
    NavigationStack {
        ReportView(service: MockReportService(latency: .zero), request: DemoScenario.red.makeRequest(),
                   expandAll: true) {}
    }
}
