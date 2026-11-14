import SwiftUI

struct AboutView: View {
    @Environment(\.dismiss) private var dismiss

    private var version: String {
        Bundle.main.object(forInfoDictionaryKey: "CFBundleShortVersionString") as? String ?? "–"
    }

    var body: some View {
        NavigationStack {
            List {
                Section("What it is") {
                    Text("Férový nájem compares a rental offer with public data. It gives indicative information, not a legal assessment.")
                }
                Section("Data sources") {
                    SourceRow(name: "ČÚZK – API KN, RÚIAN", detail: "Cadastre of Real Estate, CC BY 4.0")
                    SourceRow(name: "MF ČR", detail: "Rent price map (cenová mapa nájemního bydlení)")
                    SourceRow(name: "ARES, ISIR", detail: "Business and insolvency registers")
                    SourceRow(name: "Záplavová území", detail: "Flood zones")
                }
                Section("Privacy") {
                    Label("Reports are not stored on our servers.", systemImage: "server.rack")
                    Label("Recent checks stay on this phone.", systemImage: "iphone")
                    Label("We never show or store owner names.", systemImage: "person.crop.circle.badge.xmark")
                }
                Section {
                    LabeledContent("Version", value: version)
                }
            }
            .navigationTitle("About")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .confirmationAction) { Button("Done") { dismiss() } }
            }
        }
    }
}

private struct SourceRow: View {
    let name: String
    let detail: LocalizedStringKey

    var body: some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(verbatim: name)
            Text(detail).font(.footnote).foregroundStyle(.secondary)
        }
    }
}

#Preview { AboutView() }
