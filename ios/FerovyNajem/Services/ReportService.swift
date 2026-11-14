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
    case attestationUnknownKey
    case attestationFailed
}

/// Talks to the FastAPI backend. Base URL comes from Info.plist (APIBaseURL build setting).
struct APIReportService: ReportService, AttestAPI {
    let baseURL: URL
    var session: URLSession = .shared
    var attest: AppAttestClient = .shared

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
        // The exact bytes sent are the bytes signed by App Attest.
        let body = try APICoding.encoder.encode(request)
        for attempt in 0..<2 {
            var r = URLRequest(url: baseURL.appending(path: "v1/report"))
            r.httpMethod = "POST"
            r.setValue("application/json", forHTTPHeaderField: "Content-Type")
            r.httpBody = body
            for (k, v) in await attest.headers(for: body, api: self) { r.setValue(v, forHTTPHeaderField: k) }
            do {
                return try await send(r)
            } catch APIError.attestationUnknownKey where attempt == 0 {
                await attest.reset()  // server forgot the key → attest again once
            }
        }
        throw APIError.attestationFailed
    }

    func attestChallenge() async throws -> AttestChallenge {
        var r = URLRequest(url: baseURL.appending(path: "v1/attest/challenge"))
        r.httpMethod = "POST"
        return try await send(r)
    }

    func attestRegister(keyId: String, attestation: String, challenge: String) async throws {
        var r = URLRequest(url: baseURL.appending(path: "v1/attest/register"))
        r.httpMethod = "POST"
        r.setValue("application/json", forHTTPHeaderField: "Content-Type")
        r.httpBody = try JSONEncoder().encode(
            ["key_id": keyId, "attestation": attestation, "challenge": challenge]
        )
        let _: Empty = try await send(r)
    }

    private struct Empty: Decodable {}

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
        case 204 where T.self == Empty.self: return Empty() as! T
        case 401:
            let code = (try? JSONDecoder().decode(ErrorBody.self, from: data))?.detail.code
            throw code == "attestation_unknown_key" ? APIError.attestationUnknownKey : APIError.attestationFailed
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

private struct ErrorBody: Decodable {
    struct Detail: Decodable { let code: String }
    let detail: Detail
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
