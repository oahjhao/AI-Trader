// Dataset Selector Module
// Dynamically lists available agent data folders from nginx autoindex JSON API
// and provides a grouped <select> dropdown for choosing one agent to load.

class DatasetSelector {
    constructor() {
        this.folders = [];
        this.grouped = {};       // { dateSuffix: [folderName, ...] }
        this.currentFolder = null;
        this.baseDataPath = './data';
        this.dataDir = 'agent_data_astock';
        this.storageKey = 'aitrader_selected_dataset';
        this._selectEl = null;
        this._ready = false;
    }

    // ---- Public API ----

    // Initialize: fetch folder list, render selector, restore last choice
    async init(containerSelector) {
        const container = document.querySelector(containerSelector);
        if (!container) {
            console.error('[DatasetSelector] container not found:', containerSelector);
            return;
        }

        // Create the <select> element
        this._selectEl = document.createElement('select');
        this._selectEl.id = 'datasetSelect';
        this._selectEl.className = 'dataset-select';

        // Placeholder
        const placeholder = document.createElement('option');
        placeholder.value = '';
        placeholder.textContent = '⏳ Loading datasets...';
        placeholder.disabled = true;
        placeholder.selected = true;
        this._selectEl.appendChild(placeholder);
        container.appendChild(this._selectEl);

        // Fetch folders
        try {
            await this._fetchFolders();
            this._buildGrouped();
            this._renderOptions();
            this._ready = true;

            // Restore last selection
            const saved = localStorage.getItem(this.storageKey);
            if (saved && this.folders.includes(saved)) {
                this._selectEl.value = saved;
                this.currentFolder = saved;
            } else if (this.folders.length > 0) {
                // Default to first folder
                this._selectEl.value = this.folders[0];
                this.currentFolder = this.folders[0];
            }

            // Listen for changes
            this._selectEl.addEventListener('change', (e) => {
                this._onSelect(e.target.value);
            });

            // Fire initial event
            if (this.currentFolder) {
                this._onSelect(this.currentFolder);
            }
        } catch (err) {
            console.error('[DatasetSelector] init failed:', err);
            placeholder.textContent = '❌ Failed to load datasets';
        }
    }

    // Get currently selected folder name
    getSelectedFolder() {
        return this.currentFolder;
    }

    // Detect the correct merged price file for a given folder
    // e.g. "Test_nuts_250815" -> tries "merged_20250815.jsonl", falls back to "merged.jsonl"
    async detectMergedFile(folderName) {
        const suffix = this._extractDateSuffix(folderName);
        if (suffix) {
            const fullSuffix = this._expandDateSuffix(suffix);
            const candidatePath = `${this.baseDataPath}/A_stock/merged_${fullSuffix}.jsonl`;
            try {
                const resp = await fetch(candidatePath, { method: 'HEAD' });
                if (resp.ok) {
                    console.log(`[DatasetSelector] Using merged file: merged_${fullSuffix}.jsonl`);
                    return candidatePath;
                }
            } catch (e) {
                // Fall through
            }
        }
        console.log('[DatasetSelector] Using default merged file: merged.jsonl');
        return `${this.baseDataPath}/A_stock/merged.jsonl`;
    }

    // Detect hourly merged file
    async detectHourlyMergedFile(folderName) {
        const suffix = this._extractDateSuffix(folderName);
        if (suffix) {
            const fullSuffix = this._expandDateSuffix(suffix);
            const candidatePath = `${this.baseDataPath}/A_stock/merged_hourly_${fullSuffix}.jsonl`;
            try {
                const resp = await fetch(candidatePath, { method: 'HEAD' });
                if (resp.ok) {
                    return candidatePath;
                }
            } catch (e) { /* fall through */ }
        }
        return `${this.baseDataPath}/A_stock/merged_hourly.jsonl`;
    }

    // ---- Private ----

    async _fetchFolders() {
        // nginx autoindex_format json returns an array of objects:
        // [{"name":"folder_name","type":"directory","mtime":"..."}, ...]
        const url = `${this.baseDataPath}/${this.dataDir}/`;
        console.log('[DatasetSelector] Fetching directory listing:', url);

        const resp = await fetch(url);
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);

        const listing = await resp.json();
        this.folders = listing
            .filter(item => item.type === 'directory')
            .map(item => item.name.replace(/\/$/, ''))  // strip trailing slash
            .filter(name => name !== 'backup')           // exclude backup folder
            .sort((a, b) => {
                // Sort by date suffix descending (newest first), then by name
                const sa = this._extractDateSuffix(a) || '000000';
                const sb = this._extractDateSuffix(b) || '000000';
                if (sb !== sa) return sb.localeCompare(sa);
                return a.localeCompare(b);
            });

        console.log(`[DatasetSelector] Found ${this.folders.length} agent folders`);
    }

    _buildGrouped() {
        this.grouped = {};
        for (const folder of this.folders) {
            const suffix = this._extractDateSuffix(folder) || 'other';
            if (!this.grouped[suffix]) this.grouped[suffix] = [];
            this.grouped[suffix].push(folder);
        }
    }

    _renderOptions() {
        this._selectEl.innerHTML = '';

        // Placeholder
        const placeholder = document.createElement('option');
        placeholder.value = '';
        placeholder.textContent = `📂 Select Agent Dataset (${this.folders.length} available)`;
        placeholder.disabled = true;
        this._selectEl.appendChild(placeholder);

        // Render each date group as an optgroup
        const suffixes = Object.keys(this.grouped).sort((a, b) => {
            if (a === 'other') return 1;
            if (b === 'other') return -1;
            return b.localeCompare(a); // newest first
        });

        for (const suffix of suffixes) {
            const group = document.createElement('optgroup');
            group.label = suffix === 'other' ? 'Other' : this._formatGroupLabel(suffix);

            for (const folder of this.grouped[suffix]) {
                const opt = document.createElement('option');
                opt.value = folder;
                opt.textContent = folder;
                group.appendChild(opt);
            }

            this._selectEl.appendChild(group);
        }
    }

    _onSelect(folderName) {
        this.currentFolder = folderName;
        localStorage.setItem(this.storageKey, folderName);
        console.log(`[DatasetSelector] Selected: ${folderName}`);

        // Dispatch custom event
        window.dispatchEvent(new CustomEvent('dataset-changed', {
            detail: { folder: folderName }
        }));
    }

    // Extract 6-digit date suffix from folder name
    // "Test_nuts_250815" -> "250815"
    // "DS_pick_monk_260119" -> "260119"
    _extractDateSuffix(folderName) {
        const match = folderName.match(/(\d{6})$/);
        return match ? match[1] : null;
    }

    // Expand 6-digit suffix to 8-digit: "250815" -> "20250815"
    _expandDateSuffix(suffix) {
        if (!suffix || suffix.length !== 6) return suffix;
        const yearPrefix = parseInt(suffix.substring(0, 2)) >= 50 ? '19' : '20';
        return yearPrefix + suffix;
    }

    // Format group label: "260119" -> "2026-01-19"
    _formatGroupLabel(suffix) {
        const full = this._expandDateSuffix(suffix);
        if (full.length === 8) {
            return `${full.substring(0, 4)}-${full.substring(4, 6)}-${full.substring(6, 8)}`;
        }
        return suffix;
    }
}

// Create global instance
window.datasetSelector = new DatasetSelector();
