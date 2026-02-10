// Dataset Selector Module v2
// Two-level selection: Date Group + Agent Multi-select
// 1) Date group dropdown (e.g., 2026-02-02)
// 2) Agent checkbox picker (e.g., balanced, monk, nuts, tech)

class DatasetSelector {
    constructor() {
        this.folders = [];
        this.dateGroups = {};        // { dateSuffix: [folderName, ...] }
        this.currentDateGroup = null;
        this.selectedAgents = new Set();
        this.baseDataPath = './data';
        this.dataDir = 'agent_data_astock';
        this.storageKey = 'aitrader_v2';
        this._dateSelectEl = null;
        this._agentPickerEl = null;
        this._dropdownEl = null;
        this._ready = false;
    }

    // ---- Public API ----

    async init(containerSelector) {
        const container = document.querySelector(containerSelector);
        if (!container) {
            console.error('[DatasetSelector] container not found:', containerSelector);
            return;
        }

        // Create wrapper
        const wrapper = document.createElement('div');
        wrapper.className = 'dataset-selector-wrapper';

        // 1. Date group select
        this._dateSelectEl = document.createElement('select');
        this._dateSelectEl.id = 'dateGroupSelect';
        this._dateSelectEl.className = 'date-group-select';
        const ph = document.createElement('option');
        ph.value = '';
        ph.textContent = '⏳ Loading...';
        ph.disabled = true;
        ph.selected = true;
        this._dateSelectEl.appendChild(ph);
        wrapper.appendChild(this._dateSelectEl);

        // 2. Agent picker button + dropdown
        this._agentPickerEl = document.createElement('div');
        this._agentPickerEl.className = 'agent-picker';
        this._agentPickerEl.innerHTML = `
            <button type="button" class="agent-picker-toggle" id="agentPickerToggle">
                <span class="agent-picker-icon">👥</span>
                <span class="agent-count" id="agentCountLabel">0/0</span>
                <span class="agent-picker-caret">▾</span>
            </button>
            <div class="agent-picker-dropdown hidden" id="agentPickerDropdown">
                <div class="agent-picker-controls">
                    <button type="button" class="agent-picker-btn" id="selectAllAgents">All</button>
                    <button type="button" class="agent-picker-btn" id="selectNoneAgents">None</button>
                </div>
                <div class="agent-picker-list" id="agentPickerList"></div>
            </div>
        `;
        wrapper.appendChild(this._agentPickerEl);

        container.appendChild(wrapper);
        this._dropdownEl = document.getElementById('agentPickerDropdown');

        // Fetch folders and build UI
        try {
            await this._fetchFolders();
            this._buildDateGroups();
            this._renderDateGroupOptions();
            this._setupEventListeners();
            this._ready = true;

            // Restore saved state or default to newest group
            const saved = this._loadSavedState();
            const sortedGroups = Object.keys(this.dateGroups)
                .filter(s => s !== 'other')
                .sort((a, b) => b.localeCompare(a));
            if (this.dateGroups['other']) sortedGroups.push('other');

            if (saved && this.dateGroups[saved.dateGroup]) {
                this.currentDateGroup = saved.dateGroup;
                this._dateSelectEl.value = saved.dateGroup;
                this._renderAgentPicker();
                // Restore agent selection by prefix
                const groupFolders = this.dateGroups[saved.dateGroup];
                if (saved.agentPrefixes && saved.agentPrefixes.length > 0) {
                    for (const folder of groupFolders) {
                        const prefix = this._extractAgentPrefix(folder);
                        if (saved.agentPrefixes.includes(prefix)) {
                            this.selectedAgents.add(folder);
                        }
                    }
                }
                // If nothing restored, select all
                if (this.selectedAgents.size === 0) {
                    groupFolders.forEach(f => this.selectedAgents.add(f));
                }
            } else if (sortedGroups.length > 0) {
                this.currentDateGroup = sortedGroups[0];
                this._dateSelectEl.value = sortedGroups[0];
                this._renderAgentPicker();
                this.dateGroups[sortedGroups[0]].forEach(f => this.selectedAgents.add(f));
            }

            this._syncCheckboxes();
            this._updateToggleLabel();
            this._fireEvent();
        } catch (err) {
            console.error('[DatasetSelector] init failed:', err);
            ph.textContent = '❌ Failed to load';
        }
    }

    // Get all currently selected agent folder names
    getSelectedAgents() {
        return Array.from(this.selectedAgents);
    }

    // Legacy compat: return first selected agent
    getSelectedFolder() {
        const agents = this.getSelectedAgents();
        return agents.length > 0 ? agents[0] : null;
    }

    getCurrentDateGroup() {
        return this.currentDateGroup;
    }

    // Detect the correct merged price file for a date group or folder
    async detectMergedFile(folderNameOrDateGroup) {
        let suffix = folderNameOrDateGroup;
        if (folderNameOrDateGroup && folderNameOrDateGroup.length > 6) {
            suffix = this._extractDateSuffix(folderNameOrDateGroup);
        }
        if (suffix && suffix !== 'other') {
            const fullSuffix = this._expandDateSuffix(suffix);
            const candidatePath = `${this.baseDataPath}/A_stock/merged_${fullSuffix}.jsonl`;
            try {
                const resp = await fetch(candidatePath, { method: 'HEAD' });
                if (resp.ok) {
                    console.log(`[DatasetSelector] Using merged file: merged_${fullSuffix}.jsonl`);
                    return candidatePath;
                }
            } catch (e) { /* fall through */ }
        }
        console.log('[DatasetSelector] Using default merged file: merged.jsonl');
        return `${this.baseDataPath}/A_stock/merged.jsonl`;
    }

    async detectHourlyMergedFile(folderNameOrDateGroup) {
        let suffix = folderNameOrDateGroup;
        if (folderNameOrDateGroup && folderNameOrDateGroup.length > 6) {
            suffix = this._extractDateSuffix(folderNameOrDateGroup);
        }
        if (suffix && suffix !== 'other') {
            const fullSuffix = this._expandDateSuffix(suffix);
            const candidatePath = `${this.baseDataPath}/A_stock/merged_hourly_${fullSuffix}.jsonl`;
            try {
                const resp = await fetch(candidatePath, { method: 'HEAD' });
                if (resp.ok) return candidatePath;
            } catch (e) { /* fall through */ }
        }
        return `${this.baseDataPath}/A_stock/merged_hourly.jsonl`;
    }

    // ---- Private: Data ----

    async _fetchFolders() {
        const url = `${this.baseDataPath}/${this.dataDir}/`;
        console.log('[DatasetSelector] Fetching directory listing:', url);
        const resp = await fetch(url);
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
        const listing = await resp.json();
        this.folders = listing
            .filter(item => item.type === 'directory')
            .map(item => item.name.replace(/\/$/, ''))
            .filter(name => name !== 'backup')
            .sort();
        console.log(`[DatasetSelector] Found ${this.folders.length} agent folders`);
    }

    _buildDateGroups() {
        this.dateGroups = {};
        for (const folder of this.folders) {
            const suffix = this._extractDateSuffix(folder) || 'other';
            if (!this.dateGroups[suffix]) this.dateGroups[suffix] = [];
            this.dateGroups[suffix].push(folder);
        }
        console.log(`[DatasetSelector] ${Object.keys(this.dateGroups).length} date groups`);
    }

    // ---- Private: Rendering ----

    _renderDateGroupOptions() {
        this._dateSelectEl.innerHTML = '';
        const ph = document.createElement('option');
        ph.value = '';
        ph.textContent = '📅 Select Date Group';
        ph.disabled = true;
        this._dateSelectEl.appendChild(ph);

        const suffixes = Object.keys(this.dateGroups)
            .filter(s => s !== 'other')
            .sort((a, b) => b.localeCompare(a));
        if (this.dateGroups['other']) suffixes.push('other');

        for (const suffix of suffixes) {
            const opt = document.createElement('option');
            opt.value = suffix;
            const count = this.dateGroups[suffix].length;
            opt.textContent = suffix === 'other'
                ? `Other (${count})`
                : `${this._formatDateLabel(suffix)}  (${count})`;
            this._dateSelectEl.appendChild(opt);
        }
    }

    _renderAgentPicker() {
        const list = document.getElementById('agentPickerList');
        if (!list) return;
        list.innerHTML = '';
        this.selectedAgents.clear();

        if (!this.currentDateGroup || !this.dateGroups[this.currentDateGroup]) return;

        const folders = this.dateGroups[this.currentDateGroup];
        for (const folder of folders) {
            const shortName = this._getShortName(folder);
            const label = document.createElement('label');
            label.className = 'agent-checkbox-label';
            label.innerHTML = `
                <input type="checkbox" value="${folder}" class="agent-checkbox" checked>
                <span class="agent-checkbox-name">${shortName}</span>
            `;
            list.appendChild(label);
        }
    }

    _syncCheckboxes() {
        const checkboxes = document.querySelectorAll('.agent-checkbox');
        checkboxes.forEach(cb => {
            cb.checked = this.selectedAgents.has(cb.value);
        });
    }

    _updateToggleLabel() {
        const total = this.dateGroups[this.currentDateGroup]?.length || 0;
        const selected = this.selectedAgents.size;
        const label = document.getElementById('agentCountLabel');
        if (label) label.textContent = `${selected}/${total}`;
    }

    // ---- Private: Events ----

    _setupEventListeners() {
        // Date group change
        this._dateSelectEl.addEventListener('change', (e) => {
            this.currentDateGroup = e.target.value;
            this._renderAgentPicker();
            // Select all agents in new group
            const folders = this.dateGroups[this.currentDateGroup] || [];
            folders.forEach(f => this.selectedAgents.add(f));
            this._syncCheckboxes();
            this._updateToggleLabel();
            this._saveState();
            this._fireEvent();
        });

        // Agent picker toggle
        document.getElementById('agentPickerToggle').addEventListener('click', (e) => {
            e.stopPropagation();
            this._dropdownEl.classList.toggle('hidden');
        });

        // Select all
        document.getElementById('selectAllAgents').addEventListener('click', () => {
            const folders = this.dateGroups[this.currentDateGroup] || [];
            folders.forEach(f => this.selectedAgents.add(f));
            this._syncCheckboxes();
            this._updateToggleLabel();
            this._saveState();
            this._fireEvent();
        });

        // Select none
        document.getElementById('selectNoneAgents').addEventListener('click', () => {
            this.selectedAgents.clear();
            this._syncCheckboxes();
            this._updateToggleLabel();
            this._saveState();
            this._fireEvent();
        });

        // Individual checkbox changes (delegated)
        document.getElementById('agentPickerList').addEventListener('change', (e) => {
            if (e.target.classList.contains('agent-checkbox')) {
                if (e.target.checked) {
                    this.selectedAgents.add(e.target.value);
                } else {
                    this.selectedAgents.delete(e.target.value);
                }
                this._updateToggleLabel();
                this._saveState();
                this._fireEvent();
            }
        });

        // Close dropdown on outside click
        document.addEventListener('click', (e) => {
            if (!this._agentPickerEl.contains(e.target)) {
                this._dropdownEl.classList.add('hidden');
            }
        });
    }

    _fireEvent() {
        const agents = this.getSelectedAgents();
        console.log(`[DatasetSelector] Fire event: group=${this.currentDateGroup}, agents=[${agents.join(', ')}]`);
        window.dispatchEvent(new CustomEvent('dataset-changed', {
            detail: {
                dateGroup: this.currentDateGroup,
                agents: agents,
                primaryAgent: agents[0] || null
            }
        }));
    }

    // ---- Private: Persistence ----

    _saveState() {
        const state = {
            dateGroup: this.currentDateGroup,
            agentPrefixes: this.getSelectedAgents().map(f => this._extractAgentPrefix(f))
        };
        try { localStorage.setItem(this.storageKey, JSON.stringify(state)); } catch (e) {}
    }

    _loadSavedState() {
        try {
            const raw = localStorage.getItem(this.storageKey);
            return raw ? JSON.parse(raw) : null;
        } catch { return null; }
    }

    // ---- Private: Name Helpers ----

    _extractDateSuffix(folderName) {
        const match = folderName.match(/(\d{6})$/);
        return match ? match[1] : null;
    }

    _extractAgentPrefix(folderName) {
        return folderName.replace(/_\d{6}$/, '');
    }

    _getShortName(folderName) {
        const prefix = this._extractAgentPrefix(folderName);
        return prefix
            .replace(/^DS_pick_/, '')
            .replace(/^DS_/, '')
            .replace(/^Test_/, '') || prefix;
    }

    _expandDateSuffix(suffix) {
        if (!suffix || suffix.length !== 6) return suffix;
        const yearPrefix = parseInt(suffix.substring(0, 2)) >= 50 ? '19' : '20';
        return yearPrefix + suffix;
    }

    _formatDateLabel(suffix) {
        const full = this._expandDateSuffix(suffix);
        if (full && full.length === 8) {
            return `${full.substring(0, 4)}-${full.substring(4, 6)}-${full.substring(6, 8)}`;
        }
        return suffix;
    }
}

// Create global instance
window.datasetSelector = new DatasetSelector();
