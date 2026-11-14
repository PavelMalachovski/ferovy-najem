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
    @State private var disposition: Disposition = .twoKK
    @State private var ico = ""
    @State private var answers: [ScamQuestion: Bool] = [:]
    @FocusState private var addressFocused: Bool

    private var request: ReportRequest? {
        guard let selected, let rentCZK = Int(rent), rentCZK > 0,
              let areaM2 = Double(area.replacingOccurrences(of: ",", with: ".")), areaM2 > 0
        else { return nil }
        return ReportRequest(
            address: selected, unitNumber: Int(unit), rentCZK: rentCZK, areaM2: areaM2,
            disposition: disposition, landlordICO: ico.isEmpty ? nil : ico, answers: answers
        )
    }

    var body: some View {
        Form {
            Section("Address") {
                if let selected {
                    HStack {
                        Label(selected.label, systemImage: "mappin.circle.fill")
                        Spacer()
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
                    ForEach(suggestions) { s in
                        Button {
                            selected = s
                            query = s.label
                            addressFocused = false
                        } label: {
                            Label(s.label, systemImage: "mappin.and.ellipse")
                        }
                    }
                }
            }

            Section {
                TextField("Unit number (optional)", text: $unit)
                    .keyboardType(.numberPad)
            } header: {
                Text("Flat")
            } footer: {
                Text("E.g. 12 from 1001/12. Don't have it? We'll check the building – and ask the landlord: a genuine owner knows it.")
            }

            Section {
                LabeledContent("Monthly rent") {
                    HStack(spacing: 4) {
                        TextField("0", text: $rent).keyboardType(.numberPad)
                            .multilineTextAlignment(.trailing)
                        Text(verbatim: "Kč").foregroundStyle(.secondary)
                    }
                }
                LabeledContent("Floor area") {
                    HStack(spacing: 4) {
                        TextField("0", text: $area).keyboardType(.decimalPad)
                            .multilineTextAlignment(.trailing)
                        Text(verbatim: "m²").foregroundStyle(.secondary)
                    }
                }
                Picker("Layout", selection: $disposition) {
                    ForEach(Disposition.allCases) { Text(verbatim: $0.rawValue).tag($0) }
                }
            } header: {
                Text("Rent and size")
            } footer: {
                Text("Rent without utilities and service charges.")
            }

            Section {
                TextField("IČO (optional)", text: $ico).keyboardType(.numberPad)
            } header: {
                Text("Landlord company")
            } footer: {
                Text("Only if you rent from a company.")
            }
        }
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
            Button {
                if let request { onContinue(request) }
            } label: {
                Text("Continue").frame(maxWidth: .infinity)
            }
            .buttonStyle(.borderedProminent)
            .controlSize(.large)
            .disabled(request == nil)
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

    private func fill(_ r: ReportRequest) {
        selected = r.address
        query = r.address.label
        unit = r.unitNumber.map(String.init) ?? ""
        rent = String(r.rentCZK)
        area = r.areaM2.formatted()
        disposition = r.disposition
        ico = r.landlordICO ?? ""
        answers = r.answers
    }
}

#Preview {
    NavigationStack { InputView(service: MockReportService(), showAbout: .constant(false)) { _ in } }
}
