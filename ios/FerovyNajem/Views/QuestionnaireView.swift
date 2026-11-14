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

/// Explicit yes/no per question. An unanswered question stays out of `answers`,
/// so "not answered" is never mistaken for "no".
struct QuestionnaireView: View {
    let onDone: (ReportRequest) -> Void
    @State private var request: ReportRequest

    init(request: ReportRequest, onDone: @escaping (ReportRequest) -> Void) {
        _request = State(initialValue: request)
        self.onDone = onDone
    }

    private var answered: Int { request.answers.count }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 10) {
                Text("Step 2 of 2 · answer what you know")
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
                    .padding(.bottom, 4)
                ForEach(ScamQuestion.allCases) { q in
                    VStack(alignment: .leading, spacing: 10) {
                        Text(q.text).fixedSize(horizontal: false, vertical: true)
                        HStack(spacing: 8) {
                            Chip(title: Text("Yes"), selected: request.answers[q] == true,
                                 capsule: false, fill: true) { answer(q, true) }
                            Chip(title: Text("No"), selected: request.answers[q] == false,
                                 capsule: false, fill: true) { answer(q, false) }
                        }
                    }
                    .card()
                    .accessibilityElement(children: .contain)
                }
                Text("Your answers stay on this phone and only affect this report.")
                    .font(.footnote)
                    .foregroundStyle(.secondary)
                    .padding(.horizontal, 4)
            }
            .padding(.horizontal)
            .padding(.bottom, 24)
        }
        .background(Color(.systemGroupedBackground))
        .navigationTitle("A few questions")
        .toolbar {
            ToolbarItem(placement: .topBarTrailing) {
                Button("Skip") { onDone(request) }
            }
        }
        .safeAreaInset(edge: .bottom) {
            VStack(spacing: 6) {
                Text("Answered \(answered) of \(ScamQuestion.allCases.count) · no answer doesn't count as “no”")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .multilineTextAlignment(.center)
                Button {
                    onDone(request)
                } label: {
                    Text("Show report").frame(maxWidth: .infinity)
                }
                .buttonStyle(.borderedProminent)
                .controlSize(.large)
            }
            .padding(.horizontal)
            .padding(.vertical, 8)
            .background(.bar)
        }
    }

    /// Tapping the selected answer again clears it.
    private func answer(_ q: ScamQuestion, _ value: Bool) {
        request.answers[q] = request.answers[q] == value ? nil : value
    }
}

#Preview {
    NavigationStack { QuestionnaireView(request: DemoScenario.red.makeRequest()) { _ in } }
}
