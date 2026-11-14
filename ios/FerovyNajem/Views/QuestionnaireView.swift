import SwiftUI

extension ScamQuestion {
    var text: LocalizedStringKey {
        switch self {
        case .depositBeforeViewing: "Do they want a deposit before you see the flat in person?"
        case .videoOnlyViewing: "Is the viewing offered only by video or photos?"
        case .foreignAccount: "Should you pay to a foreign bank account?"
        case .ownerAbroad: "Does the landlord say they are abroad and can't meet?"
        case .pressureToPay: "Are you pushed to pay today or lose the flat?"
        case .unitNumberWithheld: "Did they avoid giving you the unit number or LV when you asked?"
        }
    }
}

struct QuestionnaireView: View {
    let onDone: (ReportRequest) -> Void
    @State private var request: ReportRequest

    init(request: ReportRequest, onDone: @escaping (ReportRequest) -> Void) {
        _request = State(initialValue: request)
        self.onDone = onDone
    }

    var body: some View {
        Form {
            Section {
                ForEach(ScamQuestion.allCases) { q in
                    Toggle(isOn: Binding(
                        get: { request.answers[q] ?? false },
                        set: { request.answers[q] = $0 }
                    )) {
                        Text(q.text).fixedSize(horizontal: false, vertical: true)
                    }
                    .padding(.vertical, 4)
                }
            } header: {
                Text("How is the deal going?")
            } footer: {
                Text("Your answers stay on this phone and only affect this report.")
            }
        }
        .navigationTitle("A few questions")
        .navigationBarTitleDisplayMode(.inline)
        .safeAreaInset(edge: .bottom) {
            Button {
                onDone(request)
            } label: {
                Text("Show report").frame(maxWidth: .infinity)
            }
            .buttonStyle(.borderedProminent)
            .controlSize(.large)
            .padding(.horizontal)
            .padding(.vertical, 8)
            .background(.bar)
        }
    }
}

#Preview {
    NavigationStack { QuestionnaireView(request: DemoScenario.red.makeRequest()) { _ in } }
}
