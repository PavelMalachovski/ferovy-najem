import XCTest
@testable import FerovyNajem

/// Decodes real responses recorded from the backend (Preview Content/Fixtures).
/// If the backend contract changes, re-record the fixtures and this test shows what broke.
final class APIContractTests: XCTestCase {
    private func load<T: Decodable>(_ name: String, as: T.Type) throws -> T {
        let url = try XCTUnwrap(
            Bundle(for: Self.self).url(forResource: name, withExtension: "json", subdirectory: "Fixtures"),
            "missing fixture \(name)"
        )
        return try APICoding.decoder.decode(T.self, from: Data(contentsOf: url))
    }

    func testGreenReport() throws {
        let r = try load("report_green", as: ReportResponse.self)
        XCTAssertEqual(r.overall, .green)
        XCTAssertEqual(r.price.verdict, .typical)
        XCTAssertNotNil(r.price.typicalLowPerM2)
        XCTAssertNotNil(r.price.periodEnd)
        XCTAssertEqual(r.property.checkLevel, "unit")
        XCTAssertEqual(r.property.unitUseName, "byt")
        XCTAssertNotNil(r.property.dataAsOf)
        XCTAssertEqual(r.landlord?.name, "ČEZ, a. s.")
        XCTAssertTrue(r.property.knDeeplink?.absoluteString.contains("typ=Jednotka") ?? false)
    }

    func testRedReport() throws {
        let r = try load("report_red", as: ReportResponse.self)
        XCTAssertEqual(r.overall, .red)
        XCTAssertEqual(r.price.verdict, .farBelow)
        XCTAssertEqual(r.landlord?.insolvency, "active")
        XCTAssertEqual(r.landlord?.insolvencyStage, "KONKURS")
        XCTAssertEqual(r.address.floodZone, "q100")
        XCTAssertTrue(r.scamFlags.flags.contains("price_far_below_reference"))
    }

    func testYellowReportBuildingLevel() throws {
        let r = try load("report_yellow", as: ReportResponse.self)
        XCTAssertEqual(r.property.hints, ["ask_unit_number"])
        XCTAssertNil(r.landlord)
    }

    func testSuggest() throws {
        let s = try load("suggest", as: [AddressSuggestion].self)
        XCTAssertFalse(s.isEmpty)
        XCTAssertGreaterThan(s[0].ruianCode, 0)
    }

    func testRequestEncodingIsSnakeCase() throws {
        var req = DemoScenario.red.makeRequest()
        req.features.newBuild = true
        let json = try XCTUnwrap(
            JSONSerialization.jsonObject(with: APICoding.encoder.encode(req)) as? [String: Any]
        )
        XCTAssertEqual(json["ruian_code"] as? Int, 73003298)
        XCTAssertEqual(json["rent_czk"] as? Int, 14000)
        XCTAssertEqual(json["area_m2"] as? Double, 60)
        XCTAssertEqual(json["landlord_ico"] as? String, "01493248")
        XCTAssertNil(json["unit_number"])          // omitted, not null
        XCTAssertNil(json["address_label"])        // UI-only
        XCTAssertEqual((json["features"] as? [String: Bool])?["new_build"], true)
        XCTAssertEqual((json["answers"] as? [String: Bool])?["deposit_before_viewing"], true)
    }

    func testInputParsing() {
        XCTAssertEqual(InputParsing.unitNumber("24"), 24)
        XCTAssertEqual(InputParsing.unitNumber("1403/24"), 24)
        XCTAssertNil(InputParsing.unitNumber("abc"))
        XCTAssertTrue(InputParsing.isValidICO("45274649"))
        XCTAssertTrue(InputParsing.isValidICO("01493248"))
        XCTAssertFalse(InputParsing.isValidICO("45274648"))
        XCTAssertFalse(InputParsing.isValidICO("123"))
    }
}
