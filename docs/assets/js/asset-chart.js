// Asset Evolution Chart
// Main page visualization - integrated with DatasetSelector

const dataLoader = new DataLoader();
window.dataLoader = dataLoader;
let chartInstance = null;
let allAgentsData = {};
let isLogScale = false;

// Color palette
const agentColors = [
    '#00d4ff', '#00ffcc', '#ff006e', '#ffbe0b',
    '#8338ec', '#3a86ff', '#fb5607', '#06ffa5'
];

// Cache for loaded SVG images
const iconImageCache = {};

function loadIconImage(iconPath) {
    return new Promise((resolve, reject) => {
        if (iconImageCache[iconPath]) {
            resolve(iconImageCache[iconPath]);
            return;
        }
        const img = new Image();
        img.onload = () => { iconImageCache[iconPath] = img; resolve(img); };
        img.onerror = reject;
        img.src = iconPath;
    });
}

// Load data and refresh UI for a selected dataset
async function loadDataAndRefresh() {
    const selectedFolder = window.datasetSelector.getSelectedFolder();
    if (!selectedFolder) {
        console.log('No dataset selected, waiting...');
        return;
    }

    showLoading();

    try {
        await dataLoader.initialize();

        console.log(`Loading data for selected dataset: ${selectedFolder}`);
        allAgentsData = await dataLoader.loadSelectedAgentData(selectedFolder);
        console.log('Data loaded:', Object.keys(allAgentsData));

        if (Object.keys(allAgentsData).length === 0) {
            hideLoading();
            document.getElementById('agent-count').textContent = '0';
            document.getElementById('trading-period').textContent = 'No data';
            document.getElementById('best-performer').textContent = '-';
            document.getElementById('avg-return').textContent = '-';
            return;
        }

        // Preload icons
        const iconPromises = Object.keys(allAgentsData).map(agentName => {
            const iconPath = dataLoader.getAgentIcon(agentName);
            return loadIconImage(iconPath).catch(() => {});
        });
        await Promise.all(iconPromises);

        // Destroy existing chart
        if (chartInstance) {
            chartInstance.destroy();
            chartInstance = null;
        }

        updateStats();
        createChart();
        createLegend();
        await createLeaderboard();

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

// Update statistics cards
function updateStats() {
    const agentNames = Object.keys(allAgentsData);
    const agentCount = agentNames.length;

    let minDate = null, maxDate = null;
    agentNames.forEach(name => {
        const history = allAgentsData[name].assetHistory;
        if (history.length > 0) {
            const firstDate = history[0].date;
            const lastDate = history[history.length - 1].date;
            if (!minDate || firstDate < minDate) minDate = firstDate;
            if (!maxDate || lastDate > maxDate) maxDate = lastDate;
        }
    });

    let bestAgent = null, bestReturn = -Infinity;
    agentNames.forEach(name => {
        const returnValue = allAgentsData[name].return;
        if (returnValue > bestReturn) {
            bestReturn = returnValue;
            bestAgent = name;
        }
    });

    document.getElementById('agent-count').textContent = agentCount;

    const formatDateRange = (dateStr) => {
        if (!dateStr) return 'N/A';
        const date = new Date(dateStr);
        return date.toLocaleString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
    };

    document.getElementById('trading-period').textContent = minDate && maxDate ?
        `${formatDateRange(minDate)} to ${formatDateRange(maxDate)}` : 'N/A';
    document.getElementById('best-performer').textContent = bestAgent ?
        dataLoader.getAgentDisplayName(bestAgent) : 'N/A';
    document.getElementById('avg-return').textContent = bestAgent ?
        dataLoader.formatPercent(bestReturn) : 'N/A';
}

// Create the main chart
function createChart() {
    const ctx = document.getElementById('assetChart').getContext('2d');

    const allDates = new Set();
    Object.keys(allAgentsData).forEach(agentName => {
        allAgentsData[agentName].assetHistory.forEach(h => allDates.add(h.date));
    });
    const sortedDates = Array.from(allDates).sort();

    const datasets = Object.keys(allAgentsData).map((agentName, index) => {
        const data = allAgentsData[agentName];
        let color, borderWidth, borderDash;

        const isBenchmark = agentName.includes('QQQ') || agentName.includes('SSE');
        if (isBenchmark) {
            color = dataLoader.getAgentBrandColor(agentName) || '#ff6b00';
            borderWidth = 2;
            borderDash = [5, 5];
        } else {
            color = dataLoader.getAgentBrandColor(agentName) || agentColors[index % agentColors.length];
            borderWidth = 3;
            borderDash = [];
        }

        const chartData = sortedDates.map(date => {
            const historyEntry = data.assetHistory.find(h => h.date === date);
            return { x: date, y: historyEntry ? historyEntry.value : null };
        });

        return {
            label: dataLoader.getAgentDisplayName(agentName),
            data: chartData,
            borderColor: color,
            backgroundColor: isBenchmark ? 'transparent' : createGradient(ctx, color),
            borderWidth: borderWidth,
            borderDash: borderDash,
            tension: 0.42,
            pointRadius: 0,
            pointHoverRadius: 7,
            pointHoverBackgroundColor: color,
            pointHoverBorderColor: '#fff',
            pointHoverBorderWidth: 3,
            fill: !isBenchmark,
            agentName: agentName,
            agentIcon: dataLoader.getAgentIcon(agentName),
            cubicInterpolationMode: 'monotone'
        };
    });

    function createGradient(ctx, color) {
        const gradient = ctx.createLinearGradient(0, 0, 0, 400);
        gradient.addColorStop(0, color + '30');
        gradient.addColorStop(0.5, color + '15');
        gradient.addColorStop(1, color + '05');
        return gradient;
    }

    // Static endpoint marker plugin (no requestAnimationFrame loop)
    const staticEndpointPlugin = {
        id: 'staticEndpoints',
        afterDatasetsDraw: (chart) => {
            const ctx = chart.ctx;

            chart.data.datasets.forEach((dataset, datasetIndex) => {
                const meta = chart.getDatasetMeta(datasetIndex);
                if (!meta.hidden && dataset.data.length > 0) {
                    // Find last non-null point
                    let lastPoint = null;
                    for (let i = meta.data.length - 1; i >= 0; i--) {
                        if (dataset.data[i]?.y !== null) {
                            lastPoint = meta.data[i];
                            break;
                        }
                    }

                    if (lastPoint) {
                        const x = lastPoint.x;
                        const y = lastPoint.y;

                        ctx.save();

                        // Static glow circle
                        ctx.shadowColor = dataset.borderColor;
                        ctx.shadowBlur = 15;
                        ctx.fillStyle = dataset.borderColor;
                        ctx.beginPath();
                        ctx.arc(x, y, 6, 0, Math.PI * 2);
                        ctx.fill();

                        // White core
                        ctx.shadowBlur = 0;
                        ctx.fillStyle = '#ffffff';
                        ctx.beginPath();
                        ctx.arc(x, y, 3, 0, Math.PI * 2);
                        ctx.fill();

                        // Icon
                        const iconSize = 28;
                        const iconX = x + 20;
                        ctx.shadowColor = dataset.borderColor;
                        ctx.shadowBlur = 10;
                        ctx.fillStyle = dataset.borderColor;
                        ctx.beginPath();
                        ctx.arc(iconX, y, iconSize / 2, 0, Math.PI * 2);
                        ctx.fill();
                        ctx.shadowBlur = 0;

                        if (iconImageCache[dataset.agentIcon]) {
                            const img = iconImageCache[dataset.agentIcon];
                            const imgSize = iconSize * 0.6;
                            ctx.drawImage(img, iconX - imgSize / 2, y - imgSize / 2, imgSize, imgSize);
                        }

                        ctx.restore();
                    }
                }
            });
            // NO requestAnimationFrame here - static render only
        }
    };

    chartInstance = new Chart(ctx, {
        type: 'line',
        data: { datasets },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            resizeDelay: 200,
            layout: { padding: { right: 50, top: 10, bottom: 10 } },
            interaction: { mode: 'index', intersect: false },
            elements: { line: { borderJoinStyle: 'round', borderCapStyle: 'round' } },
            plugins: {
                legend: { display: false },
                tooltip: {
                    enabled: false,
                    external: function(context) {
                        const tooltipModel = context.tooltip;
                        let tooltipEl = document.getElementById('chartjs-tooltip');

                        if (!tooltipEl) {
                            tooltipEl = document.createElement('div');
                            tooltipEl.id = 'chartjs-tooltip';
                            tooltipEl.innerHTML = '<div class="tooltip-container"></div>';
                            document.body.appendChild(tooltipEl);
                        }

                        if (tooltipModel.opacity === 0) {
                            tooltipEl.style.opacity = 0;
                            return;
                        }

                        if (tooltipModel.body) {
                            const dataPoints = tooltipModel.dataPoints || [];
                            const sortedPoints = [...dataPoints].sort((a, b) => (b.parsed.y || 0) - (a.parsed.y || 0));
                            const titleLines = tooltipModel.title || [];
                            let titleHtml = titleLines[0] || '';

                            let innerHtml = `<div class="tooltip-title">${titleHtml}</div><div class="tooltip-body">`;
                            sortedPoints.forEach((dataPoint, index) => {
                                const dataset = dataPoint.dataset;
                                const value = dataPoint.parsed.y;
                                const icon = dataLoader.getAgentIcon(dataset.agentName);
                                const color = dataset.borderColor;
                                innerHtml += `
                                    <div class="tooltip-row">
                                        <span class="rank-badge">#${index + 1}</span>
                                        <img src="${icon}" class="tooltip-icon" alt="">
                                        <span class="tooltip-label" style="color: ${color}">${dataset.label}</span>
                                        <span class="tooltip-value">${dataLoader.formatCurrency(value)}</span>
                                    </div>`;
                            });
                            innerHtml += '</div>';

                            tooltipEl.querySelector('.tooltip-container').innerHTML = innerHtml;
                        }

                        const position = context.chart.canvas.getBoundingClientRect();
                        const tooltipWidth = tooltipEl.offsetWidth || 300;
                        const tooltipHeight = tooltipEl.offsetHeight || 200;
                        let left = position.left + window.pageXOffset + tooltipModel.caretX + 15;
                        let top = position.top + window.pageYOffset + tooltipModel.caretY - 15;

                        if (left + tooltipWidth > window.innerWidth - 20)
                            left = position.left + window.pageXOffset + tooltipModel.caretX - tooltipWidth - 15;
                        if (top + tooltipHeight > window.innerHeight - 20)
                            top = window.innerHeight - tooltipHeight - 20;
                        if (top < 20) top = 20;
                        if (left < 20) left = 20;

                        tooltipEl.style.opacity = 1;
                        tooltipEl.style.position = 'absolute';
                        tooltipEl.style.left = left + 'px';
                        tooltipEl.style.top = top + 'px';
                        tooltipEl.style.pointerEvents = 'none';
                        tooltipEl.style.transition = 'opacity 0.2s ease';
                    }
                }
            },
            scales: {
                x: {
                    type: 'category',
                    labels: sortedDates,
                    grid: { color: 'rgba(45, 55, 72, 0.3)', drawBorder: false },
                    ticks: {
                        color: '#a0aec0',
                        maxRotation: 45, minRotation: 45,
                        autoSkip: true, maxTicksLimit: 15,
                        font: { size: 11 },
                        callback: function(value) {
                            const dateStr = this.getLabelForValue(value);
                            if (!dateStr) return '';
                            if (dateStr.includes(':')) {
                                const date = new Date(dateStr);
                                const month = (date.getMonth() + 1).toString().padStart(2, '0');
                                const day = date.getDate().toString().padStart(2, '0');
                                const hour = date.getHours().toString().padStart(2, '0');
                                return `${month}/${day} ${hour}:00`;
                            }
                            return dateStr;
                        }
                    }
                },
                y: {
                    type: isLogScale ? 'logarithmic' : 'linear',
                    grid: { color: 'rgba(45, 55, 72, 0.3)', drawBorder: false },
                    ticks: {
                        color: '#a0aec0',
                        callback: function(value) { return dataLoader.formatCurrency(value); },
                        font: { size: 11 }
                    }
                }
            }
        },
        plugins: [staticEndpointPlugin]
    });
}

// Create legend
function createLegend() {
    const legendContainer = document.getElementById('agentLegend');
    legendContainer.innerHTML = '';

    Object.keys(allAgentsData).forEach((agentName, index) => {
        const data = allAgentsData[agentName];
        const isBenchmark = agentName.includes('QQQ') || agentName.includes('SSE');
        const color = dataLoader.getAgentBrandColor(agentName) || agentColors[index % agentColors.length];
        const borderStyle = isBenchmark ? 'dashed' : 'solid';
        const returnValue = data.return;
        const returnClass = returnValue >= 0 ? 'positive' : 'negative';
        const iconPath = dataLoader.getAgentIcon(agentName);
        const brandColor = dataLoader.getAgentBrandColor(agentName);

        const legendItem = document.createElement('div');
        legendItem.className = 'legend-item';
        legendItem.innerHTML = `
            <div class="legend-icon" ${brandColor ? `style="background: ${brandColor}20;"` : ''}>
                <img src="${iconPath}" alt="${agentName}" class="legend-icon-img" />
            </div>
            <div class="legend-color" style="background: ${color}; border-style: ${borderStyle};"></div>
            <div class="legend-info">
                <div class="legend-name">${dataLoader.getAgentDisplayName(agentName)}</div>
                <div class="legend-return ${returnClass}">${dataLoader.formatPercent(returnValue)}</div>
            </div>
        `;
        legendContainer.appendChild(legendItem);
    });
}

// Toggle scale
function toggleScale() {
    isLogScale = !isLogScale;
    document.getElementById('toggle-log').textContent = isLogScale ? 'Log Scale' : 'Linear Scale';
    if (chartInstance) chartInstance.destroy();
    createChart();
}

// Export chart data as CSV
function exportData() {
    let csv = 'Date,';
    const agentNames = Object.keys(allAgentsData);
    csv += agentNames.map(name => dataLoader.getAgentDisplayName(name)).join(',') + '\n';

    const allDates = new Set();
    agentNames.forEach(name => {
        allAgentsData[name].assetHistory.forEach(h => allDates.add(h.date));
    });
    const sortedDates = Array.from(allDates).sort();

    sortedDates.forEach(date => {
        const row = [date];
        agentNames.forEach(name => {
            const entry = allAgentsData[name].assetHistory.find(h => h.date === date);
            row.push(entry ? entry.value.toFixed(2) : '');
        });
        csv += row.join(',') + '\n';
    });

    const blob = new Blob([csv], { type: 'text/csv' });
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'aitrader_asset_evolution.csv';
    a.click();
    window.URL.revokeObjectURL(url);
}

// Set up event listeners
function setupEventListeners() {
    document.getElementById('toggle-log').addEventListener('click', toggleScale);
    document.getElementById('export-chart').addEventListener('click', exportData);

    // Scroll to top
    const scrollBtn = document.getElementById('scrollToTop');
    window.addEventListener('scroll', () => {
        if (window.pageYOffset > 300) scrollBtn.classList.add('visible');
        else scrollBtn.classList.remove('visible');
    });
    scrollBtn.addEventListener('click', () => {
        window.scrollTo({ top: 0, behavior: 'smooth' });
    });

    // Resize handler
    let resizeTimeout;
    window.addEventListener('resize', () => {
        clearTimeout(resizeTimeout);
        resizeTimeout = setTimeout(() => {
            if (chartInstance) { chartInstance.resize(); chartInstance.update('none'); }
        }, 100);
    });
}

// Create leaderboard
async function createLeaderboard() {
    const leaderboard = await window.transactionLoader.buildLeaderboard(allAgentsData);
    const container = document.getElementById('leaderboardList');
    container.innerHTML = '';

    leaderboard.forEach((item, index) => {
        const rankClass = index === 0 ? 'first' : index === 1 ? 'second' : index === 2 ? 'third' : '';
        const gainClass = item.gain >= 0 ? 'positive' : 'negative';

        const itemEl = document.createElement('div');
        itemEl.className = 'leaderboard-item';
        itemEl.style.animationDelay = `${index * 0.05}s`;
        itemEl.innerHTML = `
            <div class="leaderboard-rank ${rankClass}">#${item.rank}</div>
            <div class="leaderboard-icon">
                <img src="${item.icon}" alt="${item.displayName}">
            </div>
            <div class="leaderboard-info">
                <div class="leaderboard-name">${item.displayName}</div>
                <div class="leaderboard-value">${window.transactionLoader.formatCurrency(item.currentValue)}</div>
            </div>
            <div class="leaderboard-gain">
                <div class="gain-amount ${gainClass}">${window.transactionLoader.formatCurrency(item.gain)}</div>
                <div class="gain-percent ${gainClass}">${window.transactionLoader.formatPercent(item.gainPercent)}</div>
            </div>
        `;
        container.appendChild(itemEl);
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
