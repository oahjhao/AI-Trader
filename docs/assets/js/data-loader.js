// Data Loader Utility
// Handles loading and processing all trading data
// Supports dynamic single-agent loading via dataset-selector

class DataLoader {
    constructor() {
        this.agentData = {};
        this.priceCache = {};
        this.priceRecentCache = {};
        this.priceIndexMap = {};      // symbol -> Map(date -> priceObj) for fast lookup
        this.recentIndexMap = {};     // symbol -> Map(date -> priceObj) for fast lookup
        this.config = null;
        this.baseDataPath = './data';
        this.currentMarket = 'cn';
        this._mergedFilePath = null;  // dynamic merged file path
        this._hourlyFilePath = null;  // dynamic hourly merged file path
    }

    // Switch market between US stocks and A-shares
    setMarket(market) {
        this.currentMarket = market;
        this.agentData = {};
        this.priceCache = {};
        this.priceRecentCache = {};
        this.priceIndexMap = {};
        this.recentIndexMap = {};
        this._mergedFilePath = null;
        this._hourlyFilePath = null;
    }

    // Get current market
    getMarket() {
        return this.currentMarket;
    }

    // Get current market configuration
    getMarketConfig() {
        return window.configLoader.getMarketConfig(this.currentMarket);
    }

    // Initialize with configuration
    async initialize() {
        if (!this.config) {
            this.config = await window.configLoader.loadConfig();
            this.baseDataPath = window.configLoader.getDataPath();
        }
    }

    // Set the merged file path for the current dataset
    setMergedFilePath(path) {
        this._mergedFilePath = path;
        // Clear price caches since merged file changed
        this.priceCache = {};
        this.priceRecentCache = {};
        this.priceIndexMap = {};
        this.recentIndexMap = {};
    }

    setHourlyFilePath(path) {
        this._hourlyFilePath = path;
        this.priceRecentCache = {};
        this.recentIndexMap = {};
    }

    // Load position data for a specific agent folder
    async loadAgentPositions(agentName) {
        try {
            const agentDataDir = 'agent_data_astock';
            const response = await fetch(`${this.baseDataPath}/${agentDataDir}/${agentName}/position/position.jsonl`);
            if (!response.ok) throw new Error(`Failed to load positions for ${agentName}`);

            const text = await response.text();
            const lines = text.trim().split('\n').filter(line => line.trim() !== '');
            const positions = lines.map(line => {
                try {
                    return JSON.parse(line);
                } catch (parseError) {
                    console.error(`Error parsing line for ${agentName}:`, line, parseError);
                    return null;
                }
            }).filter(pos => pos !== null);

            console.log(`Loaded ${positions.length} positions for ${agentName}`);
            return positions;
        } catch (error) {
            console.error(`Error loading positions for ${agentName}:`, error);
            return [];
        }
    }

    // Load all A-share stock names from sse_pick.csv
    async getSymbolName(symbol) {
        try {
            const response = await fetch(`${this.baseDataPath}/A_stock/sse_pick.csv`);
            if (!response.ok) throw new Error('Failed to load A-share names');

            const text = await response.text();
            const lines = text.trim().split('\n');

            for (const line of lines) {
                if (!line.trim()) continue;
                const [sym, value] = line.split(',');
                if (symbol === sym) {
                    return value;
                }
            }
        } catch (error) {
            console.error('Error getSymbolName:', error);
            return {};
        }
    }

    // Build a fast index Map from price data: symbol -> Map(dateStr -> priceObj)
    _buildPriceIndex(priceCache, targetMap) {
        for (const [symbol, timeSeries] of Object.entries(priceCache)) {
            const dateMap = new Map();
            for (const [dateStr, priceObj] of Object.entries(timeSeries)) {
                dateMap.set(dateStr, priceObj);
            }
            targetMap[symbol] = dateMap;
        }
    }

    // Load A-share hourly prices
    async loadAStockPricesRecent(symbolName) {
        if (Object.keys(this.priceRecentCache).length > 0) {
            return this.priceRecentCache[symbolName];
        }

        try {
            const filePath = this._hourlyFilePath || `${this.baseDataPath}/A_stock/merged_hourly.jsonl`;
            const response = await fetch(filePath);
            if (!response.ok) throw new Error('Failed to load A-share hourly prices');

            const text = await response.text();
            const lines = text.trim().split('\n');

            for (const line of lines) {
                if (!line.trim()) continue;
                const data = JSON.parse(line);
                const symbol = data['Meta Data']['2. Symbol'];
                this.priceRecentCache[symbol] = data['Time Series (60min)'];
            }

            this._buildPriceIndex(this.priceRecentCache, this.recentIndexMap);
            console.log(`Loaded hourly prices for ${Object.keys(this.priceRecentCache).length} stocks`);
            return this.priceRecentCache[symbolName];
        } catch (error) {
            console.error('Error loading A-share hourly prices:', error);
            return {};
        }
    }

    // Load all A-share stock prices from merged.jsonl (or date-suffixed variant)
    async loadAStockPrices() {
        if (Object.keys(this.priceCache).length > 0) {
            return this.priceCache;
        }

        try {
            const filePath = this._mergedFilePath || `${this.baseDataPath}/A_stock/merged.jsonl`;
            console.log(`[loadAStockPrices] Loading from: ${filePath}`);
            const response = await fetch(filePath);
            if (!response.ok) throw new Error('Failed to load A-share prices');

            const text = await response.text();
            const lines = text.trim().split('\n');

            for (const line of lines) {
                if (!line.trim()) continue;
                const data = JSON.parse(line);
                const symbol = data['Meta Data']['2. Symbol'];
                this.priceCache[symbol] = data['Time Series (Daily)'];
            }

            // Build fast index
            this._buildPriceIndex(this.priceCache, this.priceIndexMap);
            console.log(`Loaded prices for ${Object.keys(this.priceCache).length} A-share stocks`);
            return this.priceCache;
        } catch (error) {
            console.error('Error loading A-share prices:', error);
            return {};
        }
    }

    // Load price data for a specific stock symbol
    async loadStockPrice(symbol) {
        if (this.priceCache[symbol]) {
            return this.priceCache[symbol];
        }

        if (this.currentMarket === 'cn') {
            await this.loadAStockPrices();
            return this.priceCache[symbol] || null;
        }

        // For US stocks, load individual JSON files
        try {
            const priceFilePrefix = window.configLoader.getPriceFilePrefix();
            const filePath = `${this.baseDataPath}/${priceFilePrefix}${symbol}.json`;
            const response = await fetch(filePath);
            if (!response.ok) {
                console.warn(`[loadStockPrice] ❌ ${symbol}: HTTP ${response.status}`);
                throw new Error(`Failed to load price for ${symbol}`);
            }

            const data = await response.json();
            this.priceCache[symbol] = data['Time Series (60min)'] || data['Time Series (Daily)'];

            if (!this.priceCache[symbol]) {
                return null;
            }

            // Build index for this symbol
            const dateMap = new Map();
            for (const [dateStr, priceObj] of Object.entries(this.priceCache[symbol])) {
                dateMap.set(dateStr, priceObj);
            }
            this.priceIndexMap[symbol] = dateMap;

            return this.priceCache[symbol];
        } catch (error) {
            console.error(`[loadStockPrice] ❌ ${symbol}:`, error.message);
            return null;
        }
    }

    // Fast price lookup using indexed Map
    _fastPriceLookup(symbol, dateOrTimestamp, indexMap) {
        const dateMap = indexMap[symbol];
        if (!dateMap) return null;

        // Exact match
        const exact = dateMap.get(dateOrTimestamp);
        if (exact) {
            const price = exact['4. close'] || exact['4. sell price'];
            return price ? parseFloat(price) : null;
        }

        // Date-only match for CN market
        if (this.currentMarket === 'cn') {
            const dateOnly = dateOrTimestamp.split(' ')[0];
            const dateOnlyMatch = dateMap.get(dateOnly);
            if (dateOnlyMatch) {
                const price = dateOnlyMatch['4. close'] || dateOnlyMatch['4. sell price'];
                return price ? parseFloat(price) : null;
            }

            // Find closest timestamp on same date (for hourly data)
            let lastKey = null;
            for (const key of dateMap.keys()) {
                if (key.startsWith(dateOnly)) {
                    if (!lastKey || key > lastKey) lastKey = key;
                }
            }
            if (lastKey) {
                const entry = dateMap.get(lastKey);
                const price = entry['4. close'] || entry['4. sell price'];
                return price ? parseFloat(price) : null;
            }
        }

        return null;
    }

    // Get closing price for a symbol on a specific date/time (optimized)
    async getClosingPrice(symbol, dateOrTimestamp) {
        // Ensure prices are loaded
        if (!this.priceIndexMap[symbol]) {
            await this.loadStockPrice(symbol);
        }
        return this._fastPriceLookup(symbol, dateOrTimestamp, this.priceIndexMap);
    }

    // Get recent (hourly) price
    async getRecentPrice(symbol, dateOrTimestamp) {
        if (!this.recentIndexMap[symbol]) {
            await this.loadAStockPricesRecent(symbol);
        }
        return this._fastPriceLookup(symbol, dateOrTimestamp, this.recentIndexMap);
    }

    // Calculate total asset value for a position on a given date (optimized)
    async calculateAssetValue(position, date) {
        let totalValue = position.positions.CASH || 0;
        let hasMissingPrice = false;

        const symbols = Object.keys(position.positions).filter(s => s !== 'CASH');

        for (const symbol of symbols) {
            const shares = position.positions[symbol];
            if (shares > 0) {
                const price = await this.getClosingPrice(symbol, date);
                if (price && !isNaN(price)) {
                    totalValue += shares * price;
                    continue;
                }
                const recentPrice = await this.getRecentPrice(symbol, date);
                if (recentPrice && !isNaN(recentPrice)) {
                    totalValue += shares * recentPrice;
                    continue;
                }
                console.warn(`Missing price for ${symbol} on ${date}`);
                hasMissingPrice = true;
            }
        }

        if (this.currentMarket === 'cn' && hasMissingPrice) {
            return null;
        }

        return totalValue;
    }

    // Load complete data for a single agent including asset values over time
    async loadAgentData(agentName) {
        console.log(`Starting to load data for ${agentName}...`);
        const positions = await this.loadAgentPositions(agentName);
        if (positions.length === 0) {
            console.log(`No positions found for ${agentName}`);
            return null;
        }

        console.log(`Processing ${positions.length} positions for ${agentName}...`);

        let assetHistory = [];

        // Detect if data is hourly or daily
        const firstDate = positions[0]?.date || '';
        const isHourlyData = firstDate.includes(':');

        console.log(`Detected ${isHourlyData ? 'hourly' : 'daily'} data format for ${agentName}`);

        // Group positions by DATE (take last entry per date)
        const positionsByDate = {};
        positions.forEach(position => {
            let dateKey;
            if (isHourlyData) {
                dateKey = position.date.split(' ')[0];
            } else {
                dateKey = position.date;
            }

            const d = new Date(dateKey + 'T00:00:00');
            const dayOfWeek = d.getDay();
            if (dayOfWeek === 0 || dayOfWeek === 6) return;

            if (!positionsByDate[dateKey] || position.id > positionsByDate[dateKey].id) {
                positionsByDate[dateKey] = {
                    ...position,
                    dateKey: dateKey,
                    originalDate: position.date
                };
            }
        });

        const uniquePositions = Object.values(positionsByDate).sort((a, b) => {
            return a.dateKey.localeCompare(b.dateKey);
        });

        console.log(`Reduced to ${uniquePositions.length} unique daily positions for ${agentName}`);

        if (uniquePositions.length === 0) return null;

        const startDate = new Date(uniquePositions[0].dateKey + 'T00:00:00');
        const endDate = new Date(uniquePositions[uniquePositions.length - 1].dateKey + 'T00:00:00');

        const positionMap = {};
        uniquePositions.forEach(pos => { positionMap[pos.dateKey] = pos; });

        // Pre-load all prices before the calculation loop
        await this.loadAStockPrices();

        let currentPosition = null;
        for (let d = new Date(startDate); d <= endDate; d.setDate(d.getDate() + 1)) {
            const year = d.getFullYear();
            const month = String(d.getMonth() + 1).padStart(2, '0');
            const day = String(d.getDate()).padStart(2, '0');
            const dateStr = `${year}-${month}-${day}`;
            const dayOfWeek = d.getDay();

            if (dayOfWeek === 0 || dayOfWeek === 6) continue;

            if (positionMap[dateStr]) {
                currentPosition = positionMap[dateStr];
            }

            if (!currentPosition) continue;

            const assetValue = await this.calculateAssetValue(currentPosition, dateStr);

            if (assetValue === null || isNaN(assetValue)) continue;

            assetHistory.push({
                date: dateStr,
                value: assetValue,
                id: currentPosition.id,
                action: positionMap[dateStr]?.this_action || null
            });
        }

        if (assetHistory.length === 0) {
            console.error(`❌ ${agentName}: NO VALID ASSET HISTORY`);
            return null;
        }

        const result = {
            name: agentName,
            positions: positions,
            assetHistory: assetHistory,
            initialValue: assetHistory[0]?.value || 10000,
            currentValue: assetHistory[assetHistory.length - 1]?.value || 0,
            return: assetHistory.length > 0 ?
                ((assetHistory[assetHistory.length - 1].value - assetHistory[0].value) / assetHistory[0].value * 100) : 0
        };

        console.log(`✅ ${agentName}: ${assetHistory.length} days, return: ${result.return.toFixed(2)}%`);
        return result;
    }

    // Load data for a single selected agent folder + benchmark
    async loadSelectedAgentData(folderName) {
        console.log(`[loadSelectedAgentData] Loading: ${folderName}`);

        // Detect and set merged file
        const mergedPath = await window.datasetSelector.detectMergedFile(folderName);
        const hourlyPath = await window.datasetSelector.detectHourlyMergedFile(folderName);
        this.setMergedFilePath(mergedPath);
        this.setHourlyFilePath(hourlyPath);

        // Clear previous agent data
        this.agentData = {};

        // Load the selected agent
        const data = await this.loadAgentData(folderName);
        if (data) {
            this.agentData[folderName] = data;
            console.log(`Successfully loaded ${folderName}`);
        }

        // Load benchmark
        const benchmarkData = await this.loadBenchmarkData();
        if (benchmarkData) {
            this.agentData[benchmarkData.name] = benchmarkData;
            console.log(`Successfully loaded benchmark: ${benchmarkData.name}`);
        }

        return this.agentData;
    }

    // Load benchmark data (SSE 50 for A-shares)
    async loadBenchmarkData() {
        try {
            console.log('Loading SSE 50 Index data...');
            const marketConfig = this.getMarketConfig();
            const benchmarkFile = marketConfig ? marketConfig.benchmark_file : 'A_stock/index_daily_sse_50.json';

            const response = await fetch(`${this.baseDataPath}/${benchmarkFile}`);
            if (!response.ok) throw new Error('Failed to load SSE 50 Index data');

            const data = await response.json();
            const timeSeries = data['Time Series (Daily)'];

            if (!timeSeries) {
                console.warn('SSE 50 Index data not found');
                return null;
            }

            const benchmarkName = marketConfig ? marketConfig.benchmark_display_name : 'SSE50';
            return this._createBenchmarkAssetHistory(benchmarkName, timeSeries, 'CNY');
        } catch (error) {
            console.error('Error loading SSE 50 data:', error);
            return null;
        }
    }

    // Create benchmark asset history from time series data
    _createBenchmarkAssetHistory(name, timeSeries, currency) {
        try {
            const assetHistory = [];
            const dates = Object.keys(timeSeries).sort();

            const agentNames = Object.keys(this.agentData);
            const uiConfig = window.configLoader.getUIConfig();
            let initialValue = uiConfig.initial_value;

            if (agentNames.length > 0) {
                const firstAgent = this.agentData[agentNames[0]];
                if (firstAgent && firstAgent.positions[0]) {
                    initialValue = firstAgent.positions[0]?.positions["CASH"];
                }
            }

            let startDate = null;
            let endDate = null;
            if (agentNames.length > 0) {
                agentNames.forEach(agentName => {
                    const agent = this.agentData[agentName];
                    if (agent && agent.assetHistory.length > 0) {
                        const agentStartDate = agent.assetHistory[0].date;
                        const agentEndDate = agent.assetHistory[agent.assetHistory.length - 1].date;
                        if (!startDate || agentStartDate < startDate) startDate = agentStartDate;
                        if (!endDate || agentEndDate > endDate) endDate = agentEndDate;
                    }
                });
            }

            let benchmarkStartPrice = null;
            let currentValue = initialValue;

            for (const date of dates) {
                if (startDate && date < startDate) continue;
                if (endDate && date > endDate) continue;

                const closePrice = timeSeries[date]['4. close'] || timeSeries[date]['4. sell price'];
                if (!closePrice) continue;

                const price = parseFloat(closePrice);
                if (!benchmarkStartPrice) {
                    benchmarkStartPrice = price;
                }

                const benchmarkReturn = (price - benchmarkStartPrice) / benchmarkStartPrice;
                currentValue = initialValue * (1 + benchmarkReturn);

                assetHistory.push({
                    date: date,
                    value: currentValue,
                    id: `${name.toLowerCase().replace(/\s+/g, '-')}-${date}`,
                    action: null
                });
            }

            const result = {
                name: name,
                positions: [],
                assetHistory: assetHistory,
                initialValue: initialValue,
                currentValue: assetHistory.length > 0 ? assetHistory[assetHistory.length - 1].value : initialValue,
                return: assetHistory.length > 0 ?
                    ((assetHistory[assetHistory.length - 1].value - assetHistory[0].value) / assetHistory[0].value * 100) : 0,
                currency: currency
            };

            console.log(`✅ Benchmark ${name}: ${assetHistory.length} days, return: ${result.return.toFixed(2)}%`);
            return result;
        } catch (error) {
            console.error(`Error creating benchmark for ${name}:`, error);
            return null;
        }
    }

    // Legacy: Load all agents data (kept for compatibility, now uses selected folder)
    async loadAllAgentsData() {
        // If a dataset is selected via the selector, use it
        const selected = window.datasetSelector ? window.datasetSelector.getSelectedFolder() : null;
        if (selected) {
            return await this.loadSelectedAgentData(selected);
        }
        // Fallback: empty
        console.warn('[loadAllAgentsData] No dataset selected');
        return {};
    }

    // Get current holdings for an agent (latest position on date)
    getCurrentHoldings(agentName, date) {
        const data = this.agentData[agentName];
        if (!data || !data.positions || data.positions.length === 0) return null;
        let latestPosition = {};
        for (let i = data.positions.length - 1; i >= 0; i--) {
            if (data.positions[i].date.split(' ')[0] == date) {
                latestPosition = data.positions[i];
                break;
            }
        }
        return latestPosition && latestPosition.positions ? latestPosition.positions : null;
    }

    // Get trade history for an agent on a specific date
    getTradeHistory(agentName, date) {
        const data = this.agentData[agentName];
        if (!data) return [];

        return data.positions
            .filter(p => p.this_action && p.this_action.action !== 'no_trade' && p.date == date)
            .map(p => ({
                date: p.date,
                action: p.this_action.action,
                symbol: p.this_action.symbol,
                amount: p.this_action.amount
            }))
            .reverse();
    }

    // Format number as currency
    formatCurrency(value) {
        const marketConfig = this.getMarketConfig();
        const currency = marketConfig ? marketConfig.currency : 'CNY';
        const locale = 'zh-CN';

        return new Intl.NumberFormat(locale, {
            style: 'currency',
            currency: currency,
            minimumFractionDigits: 2
        }).format(value);
    }

    // Format percentage
    formatPercent(value) {
        const sign = value >= 0 ? '+' : '';
        return `${sign}${value.toFixed(2)}%`;
    }

    // Get display name for agent
    getAgentDisplayName(agentName) {
        // For dynamically loaded agents not in config, just return the folder name
        return agentName;
    }

    // Get icon for agent
    getAgentIcon(agentName) {
        // Check config first
        const icon = window.configLoader.getIcon(agentName, this.currentMarket);
        if (icon) return icon;
        // Default to deepseek icon for astock agents
        return './figs/deepseek.svg';
    }

    // Get brand color for agent
    getAgentBrandColor(agentName) {
        const color = window.configLoader.getColor(agentName, this.currentMarket);
        if (color) return color;

        // Default colors for benchmark
        if (agentName.includes('SSE')) return '#e74c3c';
        if (agentName.includes('QQQ')) return '#ff6b00';

        // Default for agents
        return '#00d4ff';
    }

    // Legacy compatibility
    getAgentIconKey(agentName) {
        return agentName;
    }
}

// Export for use in other modules
window.DataLoader = DataLoader;
