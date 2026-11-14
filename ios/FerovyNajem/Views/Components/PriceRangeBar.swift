import SwiftUI

/// Scale centred on the MF reference rent (±40 %, widened to fit the asking price) with the
/// "typical" band, a reference tick and a marker for the asking price. Raw asking min/max are
/// not used for the axis: they are often pooled from neighbouring areas and very wide.
struct PriceRangeBar: View {
    let price: PriceBlock
    var config: ScoringConfig = .default

    private var lower: Double { min(price.referencePerM2 * 0.6, price.askingPerM2 * 0.95) }
    private var upper: Double { max(price.referencePerM2 * 1.4, price.askingPerM2 * 1.05) }

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
                            width: x(price.referencePerM2 * config.yellowAbove, w)
                                - x(price.referencePerM2 * config.yellowBelow, w),
                            height: 10
                        )
                        .offset(x: x(price.referencePerM2 * config.yellowBelow, w))
                    Rectangle()
                        .fill(Color.primary.opacity(0.6))
                        .frame(width: 2, height: 18)
                        .offset(x: x(price.referencePerM2, w) - 1)
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
                Text(verbatim: lower.czkPerM2)
                Spacer()
                Text("MF \(price.referencePerM2.czkPerM2)")
                Spacer()
                Text(verbatim: upper.czkPerM2)
            }
            .font(.caption2)
            .foregroundStyle(.secondary)
        }
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(Text("Your rent \(price.askingPerM2.czkPerM2), MF reference rent \(price.referencePerM2.czkPerM2)"))
    }
}

extension Double {
    var czk: String { formatted(.currency(code: "CZK").precision(.fractionLength(0))) }
    var czkPerM2: String { czk + "/m²" }
}
