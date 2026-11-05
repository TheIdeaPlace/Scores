//
//          AccessibleTableBridge.swift
//  SportsScores
//
//  A thin UIKit bridge that gives VoiceOver proper data-table navigation for
//  standings and box-score grids.
//
//  VoiceOver announces "row 2, column 3 of 6" when users swipe through cells
//  and automatically reads the row-header (team name) as context when
//  navigating across a row — the same behaviour as <th scope="row"> in HTML.
//
//  Key protocol hooks:
//    • accessibilityHeaderElements(forColumn:) — column header for each col
//    • accessibilityHeaderElements(forRow:)    — row header (col-0 cell) for
//                                               each data row; this is the
//                                               hook that makes VoiceOver read
//                                               the team name automatically
//    • accessibilityDataTableCellElement(forRow:column:) — individual cells
//
//  Column-0 data cells carry .none traits (NOT .header — that would make
//  VoiceOver say "heading" and break navigation).  They are associated as
//  row headers purely through accessibilityHeaderElements(forRow:).
//
//  Usage (inside a ZStack, overlaying the visual grid which is
//  .accessibilityHidden(true)):
//
//      ZStack(alignment: .topLeading) {
//          visualGrid
//              .accessibilityHidden(true)
//          AccessibleDataTable(headers: headers, rows: rows)
//              .allowsHitTesting(false)
//      }
//

import SwiftUI
import UIKit

// MARK: - Cell element

/// A single logical cell in the accessibility table.
///
/// Implements `UIAccessibilityContainerDataTableCell` so VoiceOver can
/// announce the cell's position ("row 2, column 3 of 6").
final class DataTableCellElement: UIAccessibilityElement,
    UIAccessibilityContainerDataTableCell
{
    private let _row: Int
    private let _col: Int

    init(
        container: AccessibleDataTableView,
        label: String,
        traits: UIAccessibilityTraits = .none,
        row: Int,
        col: Int
    ) {
        self._row = row
        self._col = col
        super.init(accessibilityContainer: container)
        accessibilityLabel = label
        accessibilityTraits = traits
    }

    @objc func accessibilityRowRange() -> NSRange {
        NSRange(location: _row, length: 1)
    }

    @objc func accessibilityColumnRange() -> NSRange {
        NSRange(location: _col, length: 1)
    }

    /// Opens the row, for a table that does that. Otherwise VoiceOver's double-tap lands
    /// wherever this cell's frame is on the grid below, and rows that wrap can put that on
    /// another row. A column header opens nothing, and saying it's handled keeps that tap
    /// from landing on a row too.
    override func accessibilityActivate() -> Bool {
        guard let table = accessibilityContainer as? AccessibleDataTableView,
              let open = table.onActivateRow else { return false }
        if _row > 0 { open(_row - 1) }
        return true
    }
}

// MARK: - Container view

/// An invisible UIKit view whose sole purpose is to expose a proper
/// `UIAccessibilityContainerDataTable` tree to VoiceOver.
///
/// Set `allowsHitTesting(false)` in SwiftUI so touches pass through to the
/// visual layer underneath.
final class AccessibleDataTableView: UIView,
    UIAccessibilityContainerDataTable
{

    // MARK: Public inputs
    var columnHeaders: [String] = [] { didSet { rebuild() } }
    var dataRows: [[String]] = [] { didSet { rebuild() } }

    /// Which column holds the row's identity, used as its accessibility row
    /// header. Normally 0, but wild card standings lead with a position number,
    /// so the team name — the thing that gives a cell its context — sits at 1.
    var rowHeaderColumn: Int = 0 {
        didSet { if oldValue != rowHeaderColumn { setNeedsLayout() } }
    }

    /// Called with the data row, from 0, when VoiceOver activates one of its cells. Nil for
    /// a table whose rows don't open anything.
    var onActivateRow: ((Int) -> Void)?

    /// What the row's first cell says activating it does.
    var activationHint: String? {
        didSet { if oldValue != activationHint { rebuild() } }
    }

    // MARK: Private state
    private var headerElements: [DataTableCellElement] = []
    private var rowElements: [[DataTableCellElement]] = []

    // MARK: Init

    override init(frame: CGRect) {
        super.init(frame: frame)
        accessibilityContainerType = .dataTable
        isUserInteractionEnabled = false
        backgroundColor = .clear
    }

    required init?(coder: NSCoder) {
        fatalError("init(coder:) not implemented")
    }

    // MARK: Layout

    override func layoutSubviews() {
        super.layoutSubviews()
        rebuild()
    }

    // MARK: Build elements

    private func rebuild() {
        guard !columnHeaders.isEmpty else {
            headerElements = []
            rowElements = []
            return
        }

        let ncols = columnHeaders.count
        let nrows = dataRows.count

        // Divide the view bounds into a logical grid for focus-rectangle placement.
        // Column 0 (Team / Stat name) gets 40% of width; rest split equally.
        let totalW = max(1, bounds.width)
        let totalH = max(1, bounds.height)
        // The row-header column carries the team name, so it gets the width.
        let col0W = totalW * 0.40
        let otherColW = ncols > 1 ? (totalW - col0W) / CGFloat(ncols - 1) : 0
        let rowH = totalH / CGFloat(nrows + 1)  // +1 for header

        func xOffset(col: Int) -> CGFloat {
            col == 0 ? 0 : col0W + CGFloat(col - 1) * otherColW
        }
        func colWidth(col: Int) -> CGFloat {
            col == 0 ? col0W : otherColW
        }

        func screenFrame(row: Int, col: Int) -> CGRect {
            let localFrame = CGRect(
                x: xOffset(col: col),
                y: CGFloat(row) * rowH,
                width: colWidth(col: col),
                height: rowH
            )
            return UIAccessibility.convertToScreenCoordinates(
                localFrame,
                in: self
            )
        }

        // Column header row (accessibility row 0) — .header trait so VoiceOver
        // reads these as column headers when navigating down a column.
        headerElements = columnHeaders.enumerated().map { col, title in
            let el = DataTableCellElement(
                container: self,
                label: title,
                traits: .header,
                row: 0,
                col: col
            )
            el.accessibilityFrame = screenFrame(row: 0, col: col)
            return el
        }

        // Data rows (accessibility rows 1…n).
        // Column-0 cells are row headers — they use .none traits (NOT .header,
        // which would make VoiceOver say "heading").  They are associated as row
        // headers via accessibilityHeaderElements(forRow:) below.
        rowElements = dataRows.enumerated().map { row, cols in
            cols.enumerated().map { col, label in
                let el = DataTableCellElement(
                    container: self,
                    label: label,
                    traits: .staticText,
                    row: row + 1,
                    col: col
                )
                el.accessibilityFrame = screenFrame(row: row + 1, col: col)
                if col == 0 { el.accessibilityHint = activationHint }
                return el
            }
        }
    }

    // MARK: UIAccessibilityContainerDataTable

    @objc func accessibilityRowCount() -> Int {
        dataRows.count + 1  // data rows + header row
    }

    @objc func accessibilityColumnCount() -> Int {
        columnHeaders.count
    }

    /// Column header for each column — called when VoiceOver navigates down a column.
    @objc(accessibilityHeaderElementsForColumn:)
    func accessibilityHeaderElements(forColumn column: Int)
        -> [any UIAccessibilityContainerDataTableCell]?
    {
        // Capture a local snapshot: VoiceOver calls these from a background AX thread
        // while rebuild() may run concurrently on the main thread.
        let headers = headerElements
        guard column < headers.count else { return nil }
        return [headers[column]]
    }

    /// Row header for each data row — the column-0 cell (team name / stat name).
    /// This is the equivalent of <th scope="row"> in HTML: VoiceOver reads the
    /// team name automatically as context whenever the user navigates across a row.
    /// row 0 is the column-header row itself; data rows start at 1.
    @objc(accessibilityHeaderElementsForRow:)
    func accessibilityHeaderElements(forRow row: Int)
        -> [any UIAccessibilityContainerDataTableCell]?
    {
        guard row > 0 else { return nil }  // row 0 = column-header row; no row-header for it
        let rows = rowElements  // local snapshot
        let dataRow = row - 1
        guard dataRow < rows.count, !rows[dataRow].isEmpty else { return nil }
        let headerCol = min(rowHeaderColumn, rows[dataRow].count - 1)
        return [rows[dataRow][headerCol]]
    }

    @objc func accessibilityDataTableCellElement(forRow row: Int, column: Int)
        -> (any UIAccessibilityContainerDataTableCell)?
    {
        // Capture local snapshots so bounds check and subscript access use the
        // same array state — guards against concurrent rebuild() on the main thread.
        let headers = headerElements
        let rows = rowElements
        if row == 0 {
            guard column < headers.count else { return nil }
            return headers[column]
        }
        let dataRow = row - 1
        guard dataRow < rows.count, column < rows[dataRow].count else { return nil }
        return rows[dataRow][column]
    }

    // Standard accessibility traversal (used by VoiceOver for swipe navigation)
    override var accessibilityElements: [Any]? {
        get {
            let headers = headerElements  // local snapshot
            let rows = rowElements        // local snapshot
            var all: [Any] = headers
            rows.forEach { all.append(contentsOf: $0) }
            return all
        }
        set {}
    }
}

// MARK: - SwiftUI representable

/// SwiftUI wrapper for `AccessibleDataTableView`.
///
/// Example:
/// ```swift
/// ZStack(alignment: .topLeading) {
///     visualGridView
///         .accessibilityHidden(true)
///     AccessibleDataTable(headers: headers, rows: rows)
///         .allowsHitTesting(false)
/// }
/// ```
struct AccessibleDataTable: UIViewRepresentable {
    let headers: [String]
    let rows: [[String]]
    /// Column holding each row's identity; see `AccessibleDataTableView.rowHeaderColumn`.
    var rowHeaderColumn: Int = 0
    /// See `AccessibleDataTableView.onActivateRow`.
    var onActivateRow: ((Int) -> Void)? = nil
    var activationHint: String? = nil

    func makeUIView(context: Context) -> AccessibleDataTableView {
        AccessibleDataTableView()
    }

    func updateUIView(_ uiView: AccessibleDataTableView, context: Context) {
        // Guard against redundant rebuilds
        uiView.rowHeaderColumn = rowHeaderColumn
        uiView.onActivateRow = onActivateRow
        uiView.activationHint = activationHint
        guard uiView.columnHeaders != headers || uiView.dataRows != rows else {
            return
        }
        uiView.columnHeaders = headers
        uiView.dataRows = rows
    }
}
