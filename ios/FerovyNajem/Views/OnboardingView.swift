import SwiftUI

struct OnboardingView: View {
    let onStart: () -> Void

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 28) {
                VStack(alignment: .leading, spacing: 12) {
                    Image(systemName: "house.and.flag.fill")
                        .font(.system(size: 44))
                        .foregroundStyle(.tint)
                    Text("Check before you pay the deposit")
                        .font(.largeTitle.bold())
                    Text("Enter the address and rent. In a minute you'll see what public registers say.")
                        .font(.title3)
                        .foregroundStyle(.secondary)
                }
                .padding(.top, 32)

                VStack(alignment: .leading, spacing: 20) {
                    FeatureRow(symbol: "chart.bar.fill", title: "Price",
                               text: "Compare the rent with the Ministry of Finance rent map.")
                    FeatureRow(symbol: "building.2.fill", title: "Property",
                               text: "Does the flat exist in the cadastre? Is an ownership change in progress?")
                    FeatureRow(symbol: "briefcase.fill", title: "Landlord",
                               text: "Is the company real, active and not insolvent?")
                    FeatureRow(symbol: "exclamationmark.bubble.fill", title: "Scam patterns",
                               text: "Typical warning signs from how the deal is going.")
                }

                Callout(
                    symbol: "lock.shield.fill",
                    text: Text("We never show owner names. You can check the owner yourself with your eID – we'll show you how.")
                )
            }
            .padding(.horizontal, 24)
            .padding(.bottom, 24)
        }
        .safeAreaInset(edge: .bottom) {
            Button(action: onStart) {
                Text("Get started").frame(maxWidth: .infinity)
            }
            .buttonStyle(.borderedProminent)
            .controlSize(.large)
            .padding(.horizontal, 24)
            .padding(.bottom, 8)
            .background(.bar)
        }
    }
}

private struct FeatureRow: View {
    let symbol: String
    let title: LocalizedStringKey
    let text: LocalizedStringKey

    var body: some View {
        HStack(alignment: .top, spacing: 16) {
            Image(systemName: symbol)
                .font(.title3)
                .foregroundStyle(.tint)
                .frame(width: 32)
            VStack(alignment: .leading, spacing: 2) {
                Text(title).font(.headline)
                Text(text).font(.subheadline).foregroundStyle(.secondary)
            }
        }
    }
}

#Preview { OnboardingView {} }
