import SwiftUI

/// Scale centred on the MF reference rent (±50 %, widened to fit the asking price) with the
/// "typical" band, a reference tick and a marker for the asking price. Labels name what the
/// marks are ("You", "MF") instead of printing the axis bounds, which carry no meaning.
/// Raw asking min/max are not used: they are often pooled from neighbouring areas and very wide.
struct PriceRangeBar: View {
    let price: PriceBlock
    var config: ScoringConfig = .default

    private var lower: Double { min(price.referencePerM2 * 0.5, price.askingPerM2 * 0.95) }
    private var upper: Double { max(price.referencePerM2 * 1.5, price.askingPerM2 * 1.05) }

    private func x(_ value: Double, _ width: CGFloat) -> CGFloat {
        CGFloat((value - lower) / (upper - lower)) * width
    }

    /// Keeps a centred label inside the bar's width.
    private func labelX(_ value: Double, _ width: CGFloat) -> CGFloat {
        min(max(x(value, width), 14), width - 14)
    }

    var body: some View {
        GeometryReader { geo in
            let w = geo.size.width
            ZStack(alignment: .topLeading) {
                Text("You")
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(price.status.color)
                    .fixedSize()
                    .position(x: labelX(price.askingPerM2, w), y: 8)

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
                .frame(width: w, height: 24)
                .offset(y: 18)

                Text(verbatim: "MF")
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(.secondary)
                    .fixedSize()
                    .position(x: labelX(price.referencePerM2, w), y: 52)
            }
        }
        .frame(height: 62)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(Text("Your rent \(price.askingPerM2.czkPerM2), MF reference rent \(price.referencePerM2.czkPerM2)"))
    }
}

extension Double {
    var czk: String { formatted(.currency(code: "CZK").precision(.fractionLength(0))) }
    var czkPerM2: String { czk + "/m²" }
    /// Rounded to hundreds, without currency: for ranges like "21 500–29 100 Kč".
    var hundreds: String { ((self / 100).rounded() * 100).formatted(.number.precision(.fractionLength(0))) }
}
