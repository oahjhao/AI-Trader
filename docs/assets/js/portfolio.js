// Portfolio Analysis Page
// Detailed view of individual agent portfolio - integrated with DatasetSelector

const dataLoader = new DataLoader();
window.dataLoader = dataLoader;
let allAgentsData = {};
let currentAgent = null;
let currentDate = null;
let allocationChart = null;

// Load data and refresh UI for the selected dataset
async function loadDataAndRefresh() {
    const selectedFolder = window.datasetSelector.getSelectedFolder();
    if (!selectedFolder) {
        console.log('No dataset selected');
        return;
    }

    showLoading();

    try {
        await dataLoader.initialize();
        allAgentsData = await dataLoader.loadSelectedAgentData(selectedFolder);
        console.log('Data loaded:', Object.keys(allAgentsData));

        // Populate agent selector (only non-benchmark agents)
        populateAgentSelector();

        // Use the selected folder as the current agent
        const agentName = selectedFolder;
        if (allAgentsData[agentName]) {
            currentAgent = agentName;

            // Populate date selector
            dateSelector();

            // Load last date by default
            const positions = allAgentsData[agentName].positions;
            if (positions.length > 0) {
                const lastDate = positions[positions.length - 1].date;
                currentDate = lastDate.split(' ')[0];
                document.getElementById('dateSelect').value = currentDate;
                await loadAgentPortfolio(agentName, lastDate);
            }
        }

    } catch (error) {
        console.error('Error loading data:', error);
    } finally {
        hideLoading();
    }
}

// Initialize the page
async function init() {
    setupEventListeners();

    // Listen for dataset changes BEFORE init (init fires initial event)
    window.addEventListener('dataset-changed', async (e) => {
        console.log('Dataset changed:', e.detail.folder);
        await loadDataAndRefresh();
    });

    // Initialize the dataset selector (will fire initial dataset-changed event)
    await window.datasetSelector.init('#datasetSelectorContainer');
}

// Populate agent selector dropdown
function populateAgentSelector() {
    const select = document.getElementById('agentSelect');
    select.innerHTML = '';

    Object.keys(allAgentsData).forEach(agentName => {
        // Skip benchmark entries
        if (agentName.includes('SSE') || agentName.includes('QQQ')) return;

        const option = document.createElement('option');
        option.value = agentName;
        option.textContent = dataLoader.getAgentDisplayName(agentName);
        select.appendChild(option);
    });
}

function addUniqueOption(selectElement, value, text) {
    const existingOption = Array.from(selectElement.options).find(opt => opt.value === value);
    if (!existingOption) {
        const option = document.createElement('option');
        option.value = value;
        option.textContent = text;
        selectElement.appendChild(option);
    }
}

// dateSelector dropdown
function dateSelector() {
    const select = document.getElementById('dateSelect');
    select.innerHTML = '';

    if (!currentAgent || !allAgentsData[currentAgent]) return;

    const positions = allAgentsData[currentAgent].positions;
    Object.keys(positions).forEach(key => {
        const dateValue = positions[key].date.split(' ')[0];
        addUniqueOption(select, dateValue, dateValue);
    });
}

// Load and display portfolio for selected agent
async function loadAgentPortfolio(agentName, date) {
    showLoading();

    try {
        currentAgent = agentName;
        const data = allAgentsData[agentName];
        if (!data) {
            console.warn(`No data for ${agentName}`);
            hideLoading();
            return;
        }

        await updateMetrics(data, date);
        await updateActionHistory(data, date.split(' ')[0]);
        await updateHoldingsTable(agentName, date.split(' ')[0]);
        await updateAllocationChart(agentName, date.split(' ')[0]);
        await updateTransactions(agentName, date.split(' ')[0]);

    } catch (error) {
        console.error('Error loading portfolio:', error);
    } finally {
        hideLoading();
    }
}

// Update performance metrics
async function updateMetrics(data, date) {
    let id = data.assetHistory.length - 1;
    for (; id > 0; id--) {
        if (date.split(' ')[0] === data.assetHistory[id]?.date) break;
    }

    const totalAsset = data.assetHistory[id]?.value;
    const initialValue = data.positions[0]?.positions.CASH;
    const totalReturn = data.assetHistory.length >= 0
        ? (data.assetHistory[id]?.value - initialValue) / data.assetHistory[0]?.value * 100
        : 0;
    const latestPosition = data.positions && data.positions.length > 0
        ? data.positions[data.assetHistory[id]?.id]
        : null;
    const cashPosition = latestPosition && latestPosition.positions ? latestPosition.positions.CASH || 0 : 0;
    const totalTrades = data.positions
        ? data.positions.filter(p => p.this_action && p.this_action.action !== 'no_trade' && p.date <= date).length
        : 0;

    document.getElementById('totalAsset').textContent = dataLoader.formatCurrency(totalAsset);
    document.getElementById('totalReturn').textContent = dataLoader.formatPercent(totalReturn);
    document.getElementById('totalReturn').className = `metric-value ${totalReturn >= 0 ? 'positive' : 'negative'}`;
    document.getElementById('cashPosition').textContent = dataLoader.formatCurrency(cashPosition);
    document.getElementById('totalTrades').textContent = totalTrades;
}

// Update action history table
async function updateActionHistory(data, date) {
    const tableBody = document.getElementById('actionTableBody');
    tableBody.innerHTML = '';
    const actionsHistory = data.positions
        ? data.positions.filter(p => p.this_action && p.this_action.action !== 'no_trade' && p.date.split(' ')[0] <= date).reverse()
        : [];

    actionsHistory.forEach(p => {
        const row = document.createElement('tr');
        row.innerHTML = `
            <td class="symbol">${p.this_action.symbol}</td>
            <td class="symbol">${p.this_action.action}</td>
            <td>${p.this_action.amount}</td>
            <td>${p.date}</td>
        `;
        tableBody.appendChild(row);
    });
}

// Update holdings table
async function updateHoldingsTable(agentName, date) {
    const holdings = dataLoader.getCurrentHoldings(agentName, date);
    const tableBody = document.getElementById('holdingsTableBody');
    tableBody.innerHTML = '';

    if (!holdings) return;

    let totalValue = holdings.CASH;

    const stocks = Object.entries(holdings)
        .filter(([symbol, shares]) => symbol !== 'CASH' && shares > 0);

    const holdingsData = await Promise.all(
        stocks.map(async ([symbol, shares]) => {
            const price = await dataLoader.getClosingPrice(symbol, date);
            const priceRecent = await dataLoader.getRecentPrice(symbol, date);
            const name = await dataLoader.getSymbolName(symbol);
            const marketValue = price ? shares * price : shares * priceRecent;
            totalValue += marketValue;
            const priceReturn = price ? price : priceRecent;
            return { symbol, name, shares, priceReturn, marketValue };
        })
    );

    holdingsData.sort((a, b) => b.marketValue - a.marketValue);

    holdingsData.forEach(holding => {
        const weight = (holding.marketValue / totalValue * 100).toFixed(2);
        const row = document.createElement('tr');
        row.innerHTML = `
            <td class="symbol">${holding.symbol}</td>
            <td class="symbol">${holding.name}</td>
            <td>${holding.shares}</td>
            <td>${dataLoader.formatCurrency(holding.priceReturn || 0)}</td>
            <td>${dataLoader.formatCurrency(holding.marketValue)}</td>
            <td>${weight}%</td>
        `;
        tableBody.appendChild(row);
    });

    if (holdings.CASH > 0) {
        const cashWeight = (holdings.CASH / totalValue * 100).toFixed(2);
        const cashRow = document.createElement('tr');
        cashRow.innerHTML = `
            <td class="symbol">CASH</td>
            <td>-</td>
            <td>-</td>
            <td>-</td>
            <td>${dataLoader.formatCurrency(holdings.CASH)}</td>
            <td>${cashWeight}%</td>
        `;
        tableBody.appendChild(cashRow);
    }

    if (holdingsData.length === 0 && (!holdings.CASH || holdings.CASH === 0)) {
        const noDataRow = document.createElement('tr');
        noDataRow.innerHTML = `
            <td colspan="6" style="text-align: center; color: var(--text-muted); padding: 2rem;">
                No holdings data available
            </td>
        `;
        tableBody.appendChild(noDataRow);
    }
}

// Update allocation chart (pie chart)
async function updateAllocationChart(agentName, date) {
    const holdings = dataLoader.getCurrentHoldings(agentName, date);
    if (!holdings) return;

    const allocations = [];

    for (const [symbol, shares] of Object.entries(holdings)) {
        if (symbol === 'CASH') {
            if (shares > 0) allocations.push({ label: 'CASH', value: shares });
        } else if (shares > 0) {
            const price = await dataLoader.getClosingPrice(symbol, date);
            const priceRecent = await dataLoader.getRecentPrice(symbol, date);
            const name = await dataLoader.getSymbolName(symbol);
            if (price) {
                allocations.push({ label: name, value: shares * price });
            } else {
                allocations.push({ label: name, value: shares * priceRecent });
            }
        }
    }

    allocations.sort((a, b) => b.value - a.value);

    const topAllocations = allocations.slice(0, 10);
    const othersValue = allocations.slice(10).reduce((sum, a) => sum + a.value, 0);
    if (othersValue > 0) topAllocations.push({ label: 'Others', value: othersValue });

    if (allocationChart) allocationChart.destroy();

    const ctx = document.getElementById('allocationChart').getContext('2d');
    const colors = [
        '#00d4ff', '#00ffcc', '#ff006e', '#ffbe0b', '#8338ec',
        '#3a86ff', '#fb5607', '#06ffa5', '#ff006e', '#ffbe0b', '#8338ec'
    ];

    allocationChart = new Chart(ctx, {
        type: 'doughnut',
        data: {
            labels: topAllocations.map(a => a.label),
            datasets: [{
                data: topAllocations.map(a => a.value),
                backgroundColor: colors,
                borderWidth: 2,
                borderColor: '#1a2238'
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    position: 'bottom',
                    labels: { color: '#a0aec0', padding: 15, font: { size: 12 } }
                },
                tooltip: {
                    backgroundColor: 'rgba(26, 34, 56, 0.95)',
                    titleColor: '#00d4ff',
                    bodyColor: '#fff',
                    borderColor: '#2d3748',
                    borderWidth: 1,
                    padding: 12,
                    callbacks: {
                        label: function(context) {
                            const label = context.label || '';
                            const value = dataLoader.formatCurrency(context.parsed);
                            const total = context.dataset.data.reduce((sum, v) => sum + v, 0);
                            const percentage = ((context.parsed / total) * 100).toFixed(1);
                            return `${label}: ${value} (${percentage}%)`;
                        }
                    }
                }
            }
        }
    });
}

function extractWithFollowingText(text) {
    const lines = text.split('\n');
    const results = [];
    let currentTag = null;
    let buffer = '';

    for (const line of lines) {
        const match = line.match(/^\[([^:\]]+):\s*([^\]]+)\]\s*$/);
        if (match) {
            if (currentTag) {
                results.push({ str1: currentTag.str1, str2: currentTag.str2, str3: buffer.trim() });
                buffer = '';
            }
            currentTag = { str1: match[1].trim(), str2: match[2].trim() };
        } else if (currentTag) {
            buffer += line + '\n';
        }
    }

    if (currentTag) {
        results.push({ str1: currentTag.str1, str2: currentTag.str2, str3: buffer.trim() });
    }

    return results;
}

// Update Transactions (Daily Trade Activity)
async function updateTransactions(agentName, date) {
    const timeline = document.getElementById('tradeTimeline');
    timeline.innerHTML = '';

    const thinking = await window.transactionLoader.loadAgentThinking(agentName, date, dataLoader.getMarket());
    if (!thinking) {
        timeline.innerHTML = '<p style="color: var(--text-muted);">No trade activity data available for this date.</p>';
        return;
    }

    const displayName = agentName;
    const icon = dataLoader.getAgentIcon(agentName);
    const lines = extractWithFollowingText(thinking);

    for (const line of lines) {
        const cardEl = document.createElement('div');
        cardEl.className = 'trans-card';

        let cardHTML = `
            <div class="action-header">
                <div class="action-agent-icon">
                    <img src="${icon}" alt="${displayName}">
                </div>
                <div class="action-meta">
                    <div class="action-agent-name">${displayName}</div>
                    <div class="action-details">
                        <span class="action-type sell">${line.str1}</span>
                        <span class="action-symbol">${line.str2}</span>
                    </div>
                </div>
                <div class="action-timestamp">${date}</div>
            </div>
            <div class="action-body">
                <div class="action-thinking-label">
                    <span class="thinking-icon">🧠</span>
                    Agent Reasoning
                </div>
                <div class="action-thinking" style="white-space: pre-line;">${line.str3}</div>
            </div>
        `;
        cardEl.innerHTML = cardHTML;
        timeline.appendChild(cardEl);
    }
}

// Set up event listeners
function setupEventListeners() {
    // Agent selector change
    document.getElementById('agentSelect').addEventListener('change', (e) => {
        const date = document.getElementById('dateSelect').value;
        loadAgentPortfolio(e.target.value, date);
    });

    // Date selector change
    document.getElementById('dateSelect').addEventListener('change', (e) => {
        const agentName = document.getElementById('agentSelect').value;
        loadAgentPortfolio(agentName, e.target.value);
    });

    // Excel download button
    const excelBtn = document.getElementById('downloadExcelBtn');
    if (excelBtn) {
        excelBtn.addEventListener('click', () => {
            if (!currentAgent || !allAgentsData[currentAgent]) {
                alert('Please select a dataset first.');
                return;
            }
            const data = allAgentsData[currentAgent];
            window.excelExporter.exportAgentData(currentAgent, data.positions);
        });
    }

    // Scroll to top
    const scrollBtn = document.getElementById('scrollToTop');
    window.addEventListener('scroll', () => {
        if (window.pageYOffset > 300) scrollBtn.classList.add('visible');
        else scrollBtn.classList.remove('visible');
    });
    scrollBtn.addEventListener('click', () => {
        window.scrollTo({ top: 0, behavior: 'smooth' });
    });
}

// Loading overlay controls
function showLoading() {
    document.getElementById('loadingOverlay').classList.remove('hidden');
}

function hideLoading() {
    document.getElementById('loadingOverlay').classList.add('hidden');
}

// Initialize on page load
window.addEventListener('DOMContentLoaded', init);
