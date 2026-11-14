import SwiftUI

/// One report block: icon, title, status, one-line summary, expandable details.
struct BlockCard<Details: View>: View {
    let title: LocalizedStringKey
    let symbol: String
    let status: Status
    let summary: Text
    @State var expanded: Bool
    @ViewBuilder var details: () -> Details

    init(
        _ title: LocalizedStringKey, symbol: String, status: Status, summary: Text,
        expanded: Bool = false, @ViewBuilder details: @escaping () -> Details
    ) {
        self.title = title
        self.symbol = symbol
        self.status = status
        self.summary = summary
        _expanded = State(initialValue: expanded)
        self.details = details
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            Button {
                withAnimation(.snappy) { expanded.toggle() }
            } label: {
                HStack(alignment: .top, spacing: 12) {
                    Image(systemName: symbol)
                        .font(.title3)
                        .foregroundStyle(status.color)
                        .frame(width: 32, height: 32)
                        .background(status.color.opacity(0.12), in: .rect(cornerRadius: 8))
                    VStack(alignment: .leading, spacing: 4) {
                        HStack {
                            Text(title).font(.headline)
                            Spacer()
                            StatusPill(status: status)
                        }
                        summary
                            .font(.subheadline)
                            .foregroundStyle(.secondary)
                            .multilineTextAlignment(.leading)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                    Image(systemName: "chevron.down")
                        .font(.footnote.weight(.semibold))
                        .foregroundStyle(.tertiary)
                        .rotationEffect(.degrees(expanded ? 180 : 0))
                        .padding(.top, 6)
                }
                .contentShape(.rect)
            }
            .buttonStyle(.plain)

            if expanded {
                VStack(alignment: .leading, spacing: 10) {
                    Divider()
                    details()
                }
                .padding(.top, 12)
                .transition(.opacity.combined(with: .move(edge: .top)))
            }
        }
        .padding(16)
        .background(Color(.secondarySystemGroupedBackground), in: .rect(cornerRadius: 16))
    }
}

/// Label/value line used inside card details.
struct DetailRow: View {
    let label: LocalizedStringKey
    let value: Text

    init(_ label: LocalizedStringKey, _ value: Text) {
        self.label = label
        self.value = value
    }

    var body: some View {
        HStack(alignment: .firstTextBaseline) {
            Text(label).foregroundStyle(.secondary)
            Spacer(minLength: 12)
            value.multilineTextAlignment(.trailing)
        }
        .font(.subheadline)
    }
}

/// Tinted callout for hints and notes.
struct Callout: View {
    let symbol: String
    let text: Text
    var tint: Color = .accentColor

    var body: some View {
        HStack(alignment: .top, spacing: 10) {
            Image(systemName: symbol).foregroundStyle(tint)
            text.font(.subheadline).fixedSize(horizontal: false, vertical: true)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(12)
        .background(tint.opacity(0.10), in: .rect(cornerRadius: 12))
    }
}
