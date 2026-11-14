import Foundation

protocol ReportService: Sendable {
    func suggest(_ query: String) async throws -> [AddressSuggestion]
    func report(_ request: ReportRequest) async throws -> ReportResponse
}

enum APIError: Error, Equatable {
    case offline
    case rateLimited
    case server(Int)
    case badResponse
}

/// Talks to the FastAPI backend. Base URL comes from Info.plist (APIBaseURL build setting).
struct APIReportService: ReportService {
    let baseURL: URL
    var session: URLSession = .shared

    static func fromBundle() -> APIReportService {
        let raw = Bundle.main.object(forInfoDictionaryKey: "APIBaseURL") as? String ?? ""
        return APIReportService(baseURL: URL(string: raw) ?? URL(string: "http://localhost:8000")!)
    }

    func suggest(_ query: String) async throws -> [AddressSuggestion] {
        var c = URLComponents(url: baseURL.appending(path: "v1/address/suggest"), resolvingAgainstBaseURL: false)!
        c.queryItems = [URLQueryItem(name: "q", value: query), URLQueryItem(name: "limit", value: "8")]
        return try await send(URLRequest(url: c.url!))
    }

    func report(_ request: ReportRequest) async throws -> ReportResponse {
        var r = URLRequest(url: baseURL.appending(path: "v1/report"))
        r.httpMethod = "POST"
        r.setValue("application/json", forHTTPHeaderField: "Content-Type")
        r.httpBody = try APICoding.encoder.encode(request)
        return try await send(r)
    }

    private func send<T: Decodable>(_ request: URLRequest) async throws -> T {
        var request = request
        request.timeoutInterval = 30
        request.setValue(Locale.preferredLanguages.first ?? "cs", forHTTPHeaderField: "Accept-Language")
        let data: Data
        let response: URLResponse
        do {
            (data, response) = try await session.data(for: request)
        } catch is CancellationError {
            throw CancellationError()
        } catch let e as URLError where e.code == .cancelled {
            throw CancellationError()
        } catch {
            throw APIError.offline
        }
        guard let http = response as? HTTPURLResponse else { throw APIError.badResponse }
        switch http.statusCode {
        case 200: break
        case 429: throw APIError.rateLimited
        default: throw APIError.server(http.statusCode)
        }
        do {
            return try APICoding.decoder.decode(T.self, from: data)
        } catch {
            throw APIError.badResponse
        }
    }
}

/// Offline demo/preview service backed by real responses recorded from the backend
/// (Preview Content/Fixtures; stripped from archive builds).
struct MockReportService: ReportService {
    var latency: Duration = .milliseconds(700)

    func suggest(_ query: String) async throws -> [AddressSuggestion] {
        let q = query.folding(options: [.diacriticInsensitive, .caseInsensitive], locale: nil)
        return DemoScenario.allCases.map(\.address).filter {
            $0.label.folding(options: [.diacriticInsensitive, .caseInsensitive], locale: nil).contains(q)
        }
    }

    func report(_ request: ReportRequest) async throws -> ReportResponse {
        try await Task.sleep(for: latency)
        let name: String =
            request.ruianCode == DemoScenario.red.address.ruianCode ? "report_red"
            : request.unitNumber == nil ? "report_yellow" : "report_green"
        return try Self.fixture(name)
    }

    static func fixture(_ name: String) throws -> ReportResponse {
        guard let url = Bundle.main.url(forResource: name, withExtension: "json") else {
            throw APIError.badResponse
        }
        return try APICoding.decoder.decode(ReportResponse.self, from: Data(contentsOf: url))
    }
}

/// Real addresses for demos against the live backend (DEBUG menu) and the mock.
enum DemoScenario: String, CaseIterable, Identifiable {
    case green, yellow, red
    var id: String { rawValue }

    var address: AddressSuggestion {
        switch self {
        case .green, .yellow:
            AddressSuggestion(ruianCode: 21951977, label: "U křížku 1403/4, Nusle, Praha 4", lat: 50.0623, lon: 14.4480)
        case .red:
            AddressSuggestion(ruianCode: 73003298, label: "Rohanské nábřeží 678/23, Karlín, Praha 8", lat: 50.0921, lon: 14.4381)
        }
    }

    func makeRequest() -> ReportRequest {
        let a = address
        switch self {
        case .green:
            return ReportRequest(ruianCode: a.ruianCode, addressLabel: a.label, unitNumber: 24, rentCzk: 22_900,
                                 areaM2: 55, disposition: .twoKK, landlordIco: "45274649",
                                 features: Features(lift: true))
        case .yellow:
            return ReportRequest(ruianCode: a.ruianCode, addressLabel: a.label, unitNumber: nil, rentCzk: 23_500,
                                 areaM2: 55, disposition: .twoKK, landlordIco: nil,
                                 answers: [.unitNumberWithheld: true])
        case .red:
            return ReportRequest(ruianCode: a.ruianCode, addressLabel: a.label, unitNumber: nil, rentCzk: 14_000,
                                 areaM2: 60, disposition: .twoOne, landlordIco: "01493248",
                                 answers: [.depositBeforeViewing: true, .ownerAbroad: true])
        }
    }
}
