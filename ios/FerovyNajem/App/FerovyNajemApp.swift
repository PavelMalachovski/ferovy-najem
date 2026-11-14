import SwiftUI

@main
struct FerovyNajemApp: App {
    var body: some Scene {
        WindowGroup {
            RootView(service: MockReportService())
        }
    }
}

enum Route: Hashable {
    case questionnaire(ReportRequest)
    case report(ReportRequest)
}

struct RootView: View {
    let service: any ReportService

    @AppStorage("onboarded") private var onboarded = false
    @State private var path: [Route] = []
    @State private var showAbout = false

    var body: some View {
        Group {
            if onboarded {
                NavigationStack(path: $path) {
                    InputView(service: service, showAbout: $showAbout) { path.append(.questionnaire($0)) }
                        .navigationDestination(for: Route.self) { route in
                            switch route {
                            case .questionnaire(let req):
                                QuestionnaireView(request: req) { path.append(.report($0)) }
                            case .report(let req):
                                ReportView(service: service, request: req) {
                                    path.removeAll()
                                }
                            }
                        }
                }
                .sheet(isPresented: $showAbout) { AboutView() }
            } else {
                OnboardingView { withAnimation { onboarded = true } }
            }
        }
        .onAppear(perform: applyDebugLaunchArguments)
    }

    /// DEBUG-only deep links for screenshots, e.g.
    /// `xcrun simctl launch booted cz.ferovynajem.app -screen report -demo red -expand YES -scroll bottom`
    private func applyDebugLaunchArguments() {
        #if DEBUG
        let d = UserDefaults.standard
        guard let screen = d.string(forKey: "screen") else { return }
        let demo = DemoScenario(rawValue: d.string(forKey: "demo") ?? "") ?? .green
        onboarded = screen != "onboarding"
        switch screen {
        case "questionnaire": path = [.questionnaire(demo.makeRequest())]
        case "report": path = [.report(demo.makeRequest())]
        case "about": showAbout = true
        default: path = []
        }
        #endif
    }
}
