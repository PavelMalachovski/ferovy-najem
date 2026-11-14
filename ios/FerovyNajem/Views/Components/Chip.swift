import SwiftUI

/// Selectable chip used for layout, features and yes/no answers.
/// Selection is shown by tint, border weight and a checkmark, not by colour alone.
struct Chip: View {
    let title: Text
    let selected: Bool
    var capsule = true
    var fill = false
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            HStack(spacing: 6) {
                if selected && capsule {
                    Image(systemName: "checkmark").font(.caption.bold())
                }
                title
            }
            .font(.subheadline.weight(selected ? .semibold : .regular))
            .padding(.horizontal, 14)
            .frame(maxWidth: fill ? .infinity : nil, minHeight: 44)
            .foregroundStyle(selected ? Color.accentColor : Color.primary)
            .background(
                selected ? Color.accentColor.opacity(0.12) : Color(.secondarySystemGroupedBackground),
                in: .rect(cornerRadius: capsule ? 22 : 10)
            )
            .overlay(
                RoundedRectangle(cornerRadius: capsule ? 22 : 10)
                    .strokeBorder(selected ? Color.accentColor : Color(.separator),
                                  lineWidth: selected ? 2 : 1)
            )
            .contentShape(.rect)
        }
        .buttonStyle(.plain)
        .accessibilityAddTraits(selected ? .isSelected : [])
    }
}

/// Wraps children onto new lines when they don't fit.
struct FlowLayout: Layout {
    var spacing: CGFloat = 8

    func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) -> CGSize {
        let maxWidth = proposal.width ?? .infinity
        var x: CGFloat = 0, y: CGFloat = 0, rowHeight: CGFloat = 0, widest: CGFloat = 0
        for view in subviews {
            let size = view.sizeThatFits(.unspecified)
            if x > 0 && x + size.width > maxWidth {
                y += rowHeight + spacing
                x = 0
                rowHeight = 0
            }
            x += size.width + spacing
            rowHeight = max(rowHeight, size.height)
            widest = max(widest, x - spacing)
        }
        return CGSize(width: proposal.width ?? widest, height: y + rowHeight)
    }

    func placeSubviews(in bounds: CGRect, proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) {
        var x = bounds.minX, y = bounds.minY, rowHeight: CGFloat = 0
        for view in subviews {
            let size = view.sizeThatFits(.unspecified)
            if x > bounds.minX && x + size.width > bounds.maxX {
                y += rowHeight + spacing
                x = bounds.minX
                rowHeight = 0
            }
            view.place(at: CGPoint(x: x, y: y), proposal: ProposedViewSize(size))
            x += size.width + spacing
            rowHeight = max(rowHeight, size.height)
        }
    }
}

extension View {
    /// White rounded card on the grouped background.
    func card() -> some View {
        padding(16)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(Color(.secondarySystemGroupedBackground), in: .rect(cornerRadius: 14))
    }
}

extension Text {
    /// Small grey label at the top of a card.
    func cardLabel() -> some View {
        font(.footnote.weight(.semibold)).foregroundStyle(.secondary)
    }
}
