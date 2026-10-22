import XCTest
@testable import AISADCore

final class HoverPopoverTests: XCTestCase {
    func testHoverOpensAndLeavingBothSurfacesCanDismiss() {
        var state = HoverPopoverState()
        XCTAssertFalse(state.shouldRemainOpen)
        state.setHover(true, area: .trigger)
        XCTAssertTrue(state.shouldRemainOpen)
        state.setHover(false, area: .trigger)
        XCTAssertFalse(state.shouldRemainOpen)
    }

    func testCrossingFromTriggerToDetailsKeepsTheCardOpen() {
        var state = HoverPopoverState()
        state.setHover(true, area: .trigger)
        state.setHover(false, area: .trigger)
        state.setHover(true, area: .details) // Arrives during the owned exit-grace task.
        XCTAssertTrue(state.shouldRemainOpen)
        state.setHover(false, area: .details)
        XCTAssertFalse(state.shouldRemainOpen)
    }

    func testReturningToTriggerCancelsAPendingDismissal() {
        var state = HoverPopoverState()
        state.setHover(true, area: .details)
        state.setHover(false, area: .details)
        state.setHover(true, area: .trigger)
        XCTAssertTrue(state.shouldRemainOpen)
    }

    func testKeyboardOrClickPinSurvivesPointerExit() {
        var state = HoverPopoverState()
        state.pin()
        state.setHover(true, area: .details)
        state.setHover(false, area: .details)
        XCTAssertTrue(state.shouldRemainOpen)
        XCTAssertTrue(state.isPinned)
    }

    func testDismissalOrProviderSwitchClearsThePinAndHoverState() {
        var state = HoverPopoverState()
        state.setHover(true, area: .trigger)
        state.setHover(true, area: .details)
        state.pin()
        state.dismiss()
        XCTAssertFalse(state.shouldRemainOpen)
        XCTAssertFalse(state.isPinned)
        state.setHover(true, area: .trigger)
        state.setHover(false, area: .trigger)
        XCTAssertFalse(state.shouldRemainOpen, "A later hover must not inherit the old pin")
    }
}
