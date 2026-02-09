// Excel Export Module
// Generates Excel workbooks with trade actions and position history
// Requires SheetJS (xlsx) library to be loaded

class ExcelExporter {
    constructor() {}

    // Export agent data as an Excel workbook
    // @param {string} agentName - agent folder name
    // @param {Array} positions - array of position objects from position.jsonl
    // @param {object} dataLoader - DataLoader instance for price lookups
    exportAgentData(agentName, positions) {
        if (!window.XLSX) {
            alert('Excel library not loaded. Please refresh the page.');
            return;
        }

        if (!positions || positions.length === 0) {
            alert('No position data available to export.');
            return;
        }

        const wb = XLSX.utils.book_new();

        // Sheet 1: Trade Actions
        this._addTradeActionsSheet(wb, positions);

        // Sheet 2: Position History
        this._addPositionHistorySheet(wb, positions);

        // Generate filename
        const filename = `${agentName}_report.xlsx`;

        // Download
        XLSX.writeFile(wb, filename);
        console.log(`[ExcelExporter] Downloaded: ${filename}`);
    }

    // Sheet 1: Trade Actions (buy/sell only)
    _addTradeActionsSheet(wb, positions) {
        const rows = [];
        // Header
        rows.push(['Date', 'Action', 'Symbol', 'Amount', 'Price', 'CASH After']);

        for (const pos of positions) {
            if (!pos.this_action) continue;
            const action = pos.this_action.action;
            if (action === 'no_trade' || action === 'initial') continue;

            rows.push([
                pos.date,
                action,
                pos.this_action.symbol || '',
                pos.this_action.amount || 0,
                pos.this_action.price || '',
                pos.positions?.CASH || 0
            ]);
        }

        const ws = XLSX.utils.aoa_to_sheet(rows);

        // Set column widths
        ws['!cols'] = [
            { wch: 20 },  // Date
            { wch: 8 },   // Action
            { wch: 12 },  // Symbol
            { wch: 10 },  // Amount
            { wch: 12 },  // Price
            { wch: 15 },  // CASH After
        ];

        XLSX.utils.book_append_sheet(wb, ws, 'Trade Actions');
    }

    // Sheet 2: Position History (all entries with stock shares)
    _addPositionHistorySheet(wb, positions) {
        if (positions.length === 0) return;

        // Collect all stock symbols across all positions
        const allSymbols = new Set();
        for (const pos of positions) {
            if (pos.positions) {
                for (const key of Object.keys(pos.positions)) {
                    if (key !== 'CASH') allSymbols.add(key);
                }
            }
        }
        const symbolList = Array.from(allSymbols).sort();

        // Header
        const header = ['Date', 'ID', 'Action', 'CASH', ...symbolList];
        const rows = [header];

        for (const pos of positions) {
            const actionStr = pos.this_action
                ? `${pos.this_action.action || ''} ${pos.this_action.symbol || ''} x${pos.this_action.amount || 0}`
                : 'initial';

            const row = [
                pos.date,
                pos.id,
                actionStr,
                pos.positions?.CASH || 0,
            ];

            for (const sym of symbolList) {
                row.push(pos.positions?.[sym] || 0);
            }

            rows.push(row);
        }

        const ws = XLSX.utils.aoa_to_sheet(rows);

        // Set column widths
        const cols = [
            { wch: 20 },  // Date
            { wch: 5 },   // ID
            { wch: 25 },  // Action
            { wch: 15 },  // CASH
        ];
        for (const sym of symbolList) {
            cols.push({ wch: 12 });
        }
        ws['!cols'] = cols;

        XLSX.utils.book_append_sheet(wb, ws, 'Position History');
    }
}

// Create global instance
window.excelExporter = new ExcelExporter();
