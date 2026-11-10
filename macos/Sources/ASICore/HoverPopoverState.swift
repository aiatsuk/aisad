/// Pointer/pinning state only; the view owns its cancellable exit-grace task.
public struct HoverPopoverState: Sendable {
    public enum Area: Sendable { case trigger, details }
    private var triggerHovered = false
    private var detailsHovered = false
    public private(set) var isPinned = false

    public init() {}

    public var shouldRemainOpen: Bool { triggerHovered || detailsHovered || isPinned }

    public mutating func setHover(_ inside: Bool, area: Area) {
        switch area {
        case .trigger: triggerHovered = inside
        case .details: detailsHovered = inside
        }
    }

    public mutating func pin() { isPinned = true }

    public mutating func dismiss() {
        triggerHovered = false
        detailsHovered = false
        isPinned = false
    }
}
