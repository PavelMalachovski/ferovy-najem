import CryptoKit
import DeviceCheck
import Foundation
import Security

/// Endpoints the attestation flow needs (implemented by APIReportService).
protocol AttestAPI: Sendable {
    func attestChallenge() async throws -> AttestChallenge
    func attestRegister(keyId: String, attestation: String, challenge: String) async throws
}

struct AttestChallenge: Decodable, Sendable {
    let required: Bool
    let challenge: String?
}

/// Apple App Attest client (docs/SPEC.md §4.2).
/// - Key is generated and attested once, its id kept in the Keychain.
/// - Every report body is signed (assertion); the server checks signature + counter.
/// - Unsupported devices (Simulator, old iPhones) or a server with attestation disabled → no headers.
/// Real attestation needs a device and the App Attest entitlement (set up with the Apple team, M4).
actor AppAttestClient {
    static let shared = AppAttestClient()

    private static let keychainAccount = "app-attest-key-id"
    private var keyId: String? = Keychain.read(account: keychainAccount)
    private var serverDisabled = false

    func headers(for body: Data, api: any AttestAPI) async -> [String: String] {
        let service = DCAppAttestService.shared
        guard service.isSupported, !serverDisabled else { return [:] }
        do {
            guard let id = try await ensureKey(api) else { return [:] }
            let assertion = try await service.generateAssertion(id, clientDataHash: Data(SHA256.hash(data: body)))
            return ["X-App-Attest-Key": id, "X-App-Attest-Assertion": assertion.base64EncodedString()]
        } catch {
            // Server will answer 401 if attestation is required; the UI shows that error.
            return [:]
        }
    }

    /// Server doesn't know our key (e.g. cleaned up after inactivity): attest again next time.
    func reset() {
        keyId = nil
        Keychain.delete(account: Self.keychainAccount)
    }

    private func ensureKey(_ api: any AttestAPI) async throws -> String? {
        if let keyId { return keyId }
        let challenge = try await api.attestChallenge()
        guard challenge.required, let b64 = challenge.challenge, let raw = Data(base64Encoded: b64) else {
            serverDisabled = true
            return nil
        }
        let service = DCAppAttestService.shared
        let id = try await service.generateKey()
        let attestation = try await service.attestKey(id, clientDataHash: Data(SHA256.hash(data: raw)))
        try await api.attestRegister(keyId: id, attestation: attestation.base64EncodedString(), challenge: b64)
        keyId = id
        Keychain.save(id, account: Self.keychainAccount)
        return id
    }
}

/// Minimal generic-password Keychain wrapper (this device only, after first unlock).
enum Keychain {
    private static let service = "cz.ferovynajem.app"

    static func read(account: String) -> String? {
        let q: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: account,
            kSecReturnData as String: true,
        ]
        var out: CFTypeRef?
        guard SecItemCopyMatching(q as CFDictionary, &out) == errSecSuccess, let data = out as? Data else { return nil }
        return String(data: data, encoding: .utf8)
    }

    static func save(_ value: String, account: String) {
        delete(account: account)
        let q: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: account,
            kSecAttrAccessible as String: kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly,
            kSecValueData as String: Data(value.utf8),
        ]
        SecItemAdd(q as CFDictionary, nil)
    }

    static func delete(account: String) {
        let q: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: account,
        ]
        SecItemDelete(q as CFDictionary)
    }
}
