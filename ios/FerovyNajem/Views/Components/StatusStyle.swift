import SwiftUI

extension Status {
    /// Orange instead of yellow: yellow text/icons fail contrast on light backgrounds.
    var color: Color {
        switch self {
        case .green: .green
        case .yellow: .orange
        case .red: .red
        case .unknown: .secondary
        }
    }

    var symbol: String {
        switch self {
        case .green: "checkmark.circle.fill"
        case .yellow: "exclamationmark.triangle.fill"
        case .red: "xmark.octagon.fill"
        case .unknown: "minus.circle"
        }
    }

    var label: LocalizedStringKey {
        switch self {
        case .green: "OK"
        case .yellow: "Check"
        case .red: "Serious"
        case .unknown: "Not checked"
        }
    }

    var headline: LocalizedStringResource {
        switch self {
        case .green: "No warning signs found"
        case .yellow: "A few things to check"
        case .red: "Serious warning signs"
        case .unknown: "Not enough data"
        }
    }
}

/// Colour is never the only carrier of meaning: icon + text always accompany it.
struct StatusPill: View {
    let status: Status

    var body: some View {
        Label(status.label, systemImage: status.symbol)
            .font(.caption.weight(.semibold))
            .foregroundStyle(status.color)
            .padding(.horizontal, 8)
            .padding(.vertical, 4)
            .background(status.color.opacity(0.14), in: Capsule())
            .accessibilityElement(children: .combine)
    }
}
