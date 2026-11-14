import SwiftUI

struct InputView: View {
    let service: any ReportService
    @Binding var showAbout: Bool
    let onContinue: (ReportRequest) -> Void

    @State private var query = ""
    @State private var selected: AddressSuggestion?
    @State private var suggestions: [AddressSuggestion] = []
    @State private var unit = ""
    @State private var rent = ""
    @State private var area = ""
    /// No default: the layout picks the MF size category, so a silent default skews the comparison.
    @State private var disposition: Disposition?
    @State private var ico = ""
    @State private var showICO = false
    @State private var features = FlatFeatures()
    @State private var answers: [ScamQuestion: Bool] = [:]
    @FocusState private var addressFocused: Bool

    private var rentCZK: Int? { Int(rent).flatMap { $0 > 0 ? $0 : nil } }
    private var areaM2: Double? {
        Double(area.replacingOccurrences(of: ",", with: ".")).flatMap { $0 > 0 ? $0 : nil }
    }

    private var request: ReportRequest? {
        guard let selected, let rentCZK, let areaM2, let disposition else { return nil }
        return ReportRequest(
            address: selected, unitNumber: Int(unit), rentCZK: rentCZK, areaM2: areaM2,
            disposition: disposition, landlordICO: ico.isEmpty ? nil : ico, features: features,
            answers: answers
        )
    }

    /// First missing required field, shown on the button instead of a silent disabled state.
    private var missing: LocalizedStringKey? {
        if selected == nil { return "Enter the address" }
        if rentCZK == nil { return "Enter the rent" }
        if areaM2 == nil { return "Enter the floor area" }
        if disposition == nil { return "Choose the layout" }
        return nil
    }

    private var filledCount: Int {
        [selected != nil, rentCZK != nil, areaM2 != nil, disposition != nil].filter { $0 }.count
    }

    /// Shows the rent with thousands separators while storing digits only.
    private var rentText: Binding<String> {
        Binding(
            get: { rentCZK.map { $0.formatted(.number) } ?? rent },
            set: { rent = String($0.filter(\.isNumber).prefix(7)) }
        )
    }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 14) {
                Text("Step 1 of 2 · 4 details are enough")
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
                addressCard
                HStack(alignment: .top, spacing: 12) {
                    bigField("Monthly rent", text: rentText, unit: "Kč", keyboard: .numberPad,
                             caption: Text("without utilities").foregroundStyle(.secondary))
                    bigField("Floor area", text: $area, unit: "m²", keyboard: .decimalPad,
                             caption: perM2Caption)
                }
                dispositionCard
                featuresCard
                companyCard
            }
            .padding(.horizontal)
            .padding(.bottom, 24)
        }
        .background(Color(.systemGroupedBackground))
        .scrollDismissesKeyboard(.interactively)
        .navigationTitle("New check")
        .toolbar {
            ToolbarItem(placement: .topBarTrailing) {
                Button("About", systemImage: "info.circle") { showAbout = true }
            }
            #if DEBUG
            ToolbarItem(placement: .topBarLeading) {
                Menu("Demo", systemImage: "wand.and.stars") {
                    ForEach(DemoScenario.allCases) { s in
                        Button(s.rawValue.capitalized) { fill(s.makeRequest()) }
                    }
                }
            }
            #endif
        }
        .safeAreaInset(edge: .bottom) {
            VStack(spacing: 6) {
                Button {
                    if let request { onContinue(request) }
                } label: {
                    Text(missing ?? "Continue").frame(maxWidth: .infinity)
                }
                .buttonStyle(.borderedProminent)
                .controlSize(.large)
                .disabled(request == nil)
                if missing != nil {
                    Text("\(filledCount) of 4 required details filled")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
            }
            .padding(.horizontal)
            .padding(.vertical, 8)
            .background(.bar)
        }
        .task(id: query) {
            guard selected == nil else { return }
            try? await Task.sleep(for: .milliseconds(200))
            suggestions = await service.suggest(query)
        }
    }

    // MARK: - Cards

    private var addressCard: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text("Address").cardLabel()
            if let selected {
                HStack(spacing: 10) {
                    Image(systemName: "mappin.circle.fill").font(.title3).foregroundStyle(.tint)
                    Text(verbatim: selected.label).font(.body.weight(.medium))
                    Spacer(minLength: 8)
                    Button("Change") {
                        self.selected = nil
                        addressFocused = true
                    }
                    .font(.subheadline)
                }
            } else {
                TextField("Street and house number", text: $query)
                    .textContentType(.fullStreetAddress)
                    .focused($addressFocused)
                    .padding(10)
                    .background(Color(.tertiarySystemFill), in: .rect(cornerRadius: 8))
                ForEach(suggestions) { s in
                    Button {
                        selected = s
                        query = s.label
                        addressFocused = false
                    } label: {
                        Label(s.label, systemImage: "mappin.and.ellipse")
                            .frame(maxWidth: .infinity, minHeight: 36, alignment: .leading)
                    }
                }
            }
            Divider()
            HStack(spacing: 12) {
                VStack(alignment: .leading, spacing: 2) {
                    Text("Unit number").font(.subheadline)
                    Text("Optional · e.g. 12 from 1001/12").font(.caption).foregroundStyle(.secondary)
                }
                Spacer()
                TextField(text: $unit) { Text(verbatim: "–") }
                    .keyboardType(.numberPad)
                    .multilineTextAlignment(.center)
                    .frame(width: 72, height: 40)
                    .background(Color(.tertiarySystemFill), in: .rect(cornerRadius: 8))
                    .accessibilityLabel(Text("Unit number (optional)"))
            }
        }
        .card()
    }

    private var perM2Caption: Text {
        if let rentCZK, let areaM2 {
            Text(verbatim: "= " + (Double(rentCZK) / areaM2).czkPerM2)
                .foregroundStyle(.secondary)
        } else {
            Text(verbatim: " ")
        }
    }

    private func bigField(
        _ title: LocalizedStringKey, text: Binding<String>, unit: String,
        keyboard: UIKeyboardType, caption: Text
    ) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(title).cardLabel()
            HStack(alignment: .firstTextBaseline, spacing: 4) {
                TextField(text: text) { Text(verbatim: "0") }
                    .font(.title.bold())
                    .keyboardType(keyboard)
                    .accessibilityLabel(Text(title))
                Text(verbatim: unit).foregroundStyle(.secondary)
            }
            caption.font(.caption)
        }
        .card()
    }

    private var dispositionCard: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text("Layout").cardLabel()
            LazyVGrid(columns: Array(repeating: GridItem(.flexible(), spacing: 8), count: 4), spacing: 8) {
                ForEach(Disposition.allCases) { d in
                    Chip(title: Text(verbatim: d.rawValue), selected: disposition == d,
                         capsule: false, fill: true) { disposition = d }
                }
            }
        }
        .card()
    }

    private var featuresCard: some View {
        VStack(alignment: .leading, spacing: 10) {
            (Text("What's included") + Text(verbatim: " · ") + Text("optional"))
                .font(.footnote.weight(.semibold))
                .foregroundStyle(.secondary)
            FlowLayout(spacing: 8) {
                featureChip("Lift", \.lift)
                featureChip("Balcony", \.balcony)
                featureChip("Terrace", \.terrace)
                featureChip("Furnished", \.furnished)
                featureChip("Parking", \.garage)
                featureChip("New build (up to 5 years)", \.newBuild)
            }
            Text("The MF map prices these extras separately, so we adjust the comparison.")
                .font(.caption)
                .foregroundStyle(.secondary)
        }
        .card()
    }

    private func featureChip(_ title: LocalizedStringKey, _ key: WritableKeyPath<FlatFeatures, Bool>) -> some View {
        Chip(title: Text(title), selected: features[keyPath: key]) {
            features[keyPath: key].toggle()
        }
    }

    private var companyCard: some View {
        VStack(alignment: .leading, spacing: 12) {
            Button {
                withAnimation(.snappy) { showICO.toggle() }
            } label: {
                HStack {
                    VStack(alignment: .leading, spacing: 2) {
                        Text("Renting from a company?").font(.body)
                        Text("Enter the IČO and we'll check it in ARES")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                    Spacer()
                    Image(systemName: "chevron.down")
                        .font(.footnote.weight(.semibold))
                        .foregroundStyle(.tertiary)
                        .rotationEffect(.degrees(showICO ? 180 : 0))
                }
                .contentShape(.rect)
            }
            .buttonStyle(.plain)
            if showICO {
                TextField("IČO", text: $ico)
                    .keyboardType(.numberPad)
                    .padding(10)
                    .background(Color(.tertiarySystemFill), in: .rect(cornerRadius: 8))
            }
        }
        .card()
    }

    private func fill(_ r: ReportRequest) {
        selected = r.address
        query = r.address.label
        unit = r.unitNumber.map(String.init) ?? ""
        rent = String(r.rentCZK)
        area = r.areaM2.formatted()
        disposition = r.disposition
        ico = r.landlordICO ?? ""
        showICO = !ico.isEmpty
        features = r.features
        answers = r.answers
    }
}

#Preview {
    NavigationStack { InputView(service: MockReportService(), showAbout: .constant(false)) { _ in } }
}
