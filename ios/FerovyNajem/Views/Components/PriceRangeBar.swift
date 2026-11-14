import SwiftUI

/// Horizontal scale min…max (Kč/m²) with the "typical" band around the median,
/// a median tick and a marker for the asking price.
struct PriceRangeBar: View {
    let price: PriceBlock
    var config: ScoringConfig = .default

    private var lower: Double { min(price.minPerM2, price.askingPerM2) * 0.95 }
    private var upper: Double { max(price.maxPerM2, price.askingPerM2) * 1.05 }

    private func x(_ value: Double, _ width: CGFloat) -> CGFloat {
        CGFloat((value - lower) / (upper - lower)) * width
    }

    var body: some View {
        VStack(spacing: 6) {
            GeometryReader { geo in
                let w = geo.size.width
                ZStack(alignment: .leading) {
                    Capsule().fill(Color(.tertiarySystemFill)).frame(height: 10)
                    Capsule()
                        .fill(Color.green.opacity(0.35))
                        .frame(
                            width: x(price.medianPerM2 * config.yellowAbove, w)
                                - x(price.medianPerM2 * config.yellowBelow, w),
                            height: 10
                        )
                        .offset(x: x(price.medianPerM2 * config.yellowBelow, w))
                    Rectangle()
                        .fill(Color.primary.opacity(0.6))
                        .frame(width: 2, height: 18)
                        .offset(x: x(price.medianPerM2, w) - 1)
                    Circle()
                        .fill(price.status.color)
                        .overlay(Circle().stroke(Color(.secondarySystemGroupedBackground), lineWidth: 3))
                        .frame(width: 20, height: 20)
                        .offset(x: x(price.askingPerM2, w) - 10)
                }
                .frame(height: 24)
            }
            .frame(height: 24)

            HStack {
                Text(verbatim: price.minPerM2.czkPerM2)
                Spacer()
                Text("median \(price.medianPerM2.czkPerM2)")
                Spacer()
                Text(verbatim: price.maxPerM2.czkPerM2)
            }
            .font(.caption2)
            .foregroundStyle(.secondary)
        }
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(Text("Your rent \(price.askingPerM2.czkPerM2), median \(price.medianPerM2.czkPerM2)"))
    }
}

extension Double {
    var czk: String { formatted(.currency(code: "CZK").precision(.fractionLength(0))) }
    var czkPerM2: String { czk + "/m²" }
}
