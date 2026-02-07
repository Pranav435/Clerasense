/**
 * Clerasense – Drug Comparison Module
 * Side-by-side factual comparison of 2–4 drugs.
 * Each input has fuzzy autocomplete. No ranking. No recommendations.
 * Pulls from the same verified sources as the rest of the platform.
 */

const ComparisonModule = (() => {

    /* ── Per-input autocomplete state ── */
    const _acState = {};   // { inputId: { index: -1, timer: null } }

    function render(container) {
        container.innerHTML = `
            <div class="comparison-container">
                <div class="chat-header">
                    <h2>Drug Comparison</h2>
                    <p>Compare 2–4 drugs side-by-side on factual parameters sourced from FDA, DailyMed, CMS, and FAERS.
                       No drug is ranked or recommended.</p>
                </div>
                <div class="disclaimer-banner">
                    ⚠️ Comparison displays factual, source-backed data only. No drug is ranked as "better" or "preferred."
                    Clinical decision-making must consider patient-specific factors.
                </div>
                <div class="cmp-inputs">
                    ${_renderInputSlot(1, 'e.g., Metformin', true)}
                    ${_renderInputSlot(2, 'e.g., Lisinopril', true)}
                    ${_renderInputSlot(3, 'e.g., Atorvastatin', false)}
                    ${_renderInputSlot(4, 'e.g., Omeprazole', false)}
                </div>
                <div class="cmp-actions">
                    <button id="cmp-compare-btn" class="btn btn-primary">
                        Compare Drugs
                    </button>
                    <button id="cmp-clear-btn" class="btn btn-outline btn-small" style="margin-left:8px;">
                        Clear All
                    </button>
                </div>
                <div id="cmp-results"></div>
            </div>
        `;

        // Bind buttons
        document.getElementById('cmp-compare-btn').addEventListener('click', runComparison);
        document.getElementById('cmp-clear-btn').addEventListener('click', () => {
            for (let i = 1; i <= 4; i++) {
                const el = document.getElementById(`cmp-drug-${i}`);
                if (el) el.value = '';
            }
            document.getElementById('cmp-results').innerHTML = '';
        });

        // Bind autocomplete on each input
        for (let i = 1; i <= 4; i++) {
            _bindAutocomplete(`cmp-drug-${i}`);
        }

        // Close autocomplete on outside click
        document.addEventListener('click', (e) => {
            if (!e.target.closest('.cmp-input-wrap')) {
                for (let i = 1; i <= 4; i++) _hideAc(`cmp-drug-${i}`);
            }
        });
    }

    function _renderInputSlot(n, placeholder, required) {
        const label = required ? `Drug ${n}` : `Drug ${n} <span class="cmp-optional">(optional)</span>`;
        return `
            <div class="cmp-input-wrap">
                <label>${label}</label>
                <input type="text" id="cmp-drug-${n}" class="cmp-drug-input"
                       placeholder="${placeholder}" autocomplete="off">
                <ul id="cmp-ac-${n}" class="autocomplete-list cmp-ac-list"></ul>
            </div>`;
    }

    /* ── Autocomplete per input ── */
    function _bindAutocomplete(inputId) {
        const input = document.getElementById(inputId);
        if (!input) return;
        const acId = inputId.replace('cmp-drug-', 'cmp-ac-');
        _acState[inputId] = { index: -1, timer: null };

        input.addEventListener('input', () => {
            clearTimeout(_acState[inputId].timer);
            _acState[inputId].index = -1;
            const q = input.value.trim();
            if (q.length < 2) { _hideAc(inputId); return; }
            _acState[inputId].timer = setTimeout(() => _fetchAc(inputId, q), 220);
        });

        input.addEventListener('keydown', (e) => {
            const acList = document.getElementById(acId);
            const items = acList ? acList.querySelectorAll('.autocomplete-item') : [];
            const visible = items.length > 0 && acList.style.display !== 'none';

            if (e.key === 'ArrowDown' && visible) {
                e.preventDefault();
                _acState[inputId].index = Math.min(_acState[inputId].index + 1, items.length - 1);
                _highlightItems(items, _acState[inputId].index);
            } else if (e.key === 'ArrowUp' && visible) {
                e.preventDefault();
                _acState[inputId].index = Math.max(_acState[inputId].index - 1, 0);
                _highlightItems(items, _acState[inputId].index);
            } else if (e.key === 'Enter') {
                e.preventDefault();
                if (visible && _acState[inputId].index >= 0 && items[_acState[inputId].index]) {
                    input.value = items[_acState[inputId].index].dataset.name;
                    _hideAc(inputId);
                } else {
                    _hideAc(inputId);
                }
            } else if (e.key === 'Escape') {
                _hideAc(inputId);
            } else if (e.key === 'Tab' && visible) {
                _hideAc(inputId);
            }
        });
    }

    async function _fetchAc(inputId, query) {
        const res = await API.autocompleteDrugs(query);
        const list = (res && res.suggestions) || [];
        const isFuzzy = res && res.fuzzy;
        const acId = inputId.replace('cmp-drug-', 'cmp-ac-');
        const acList = document.getElementById(acId);
        if (!acList) return;
        if (!list.length) { _hideAc(inputId); return; }

        let html = '';
        if (isFuzzy) {
            html += `<li class="autocomplete-hint">Did you mean…</li>`;
        }
        html += list.map(s =>
            `<li class="autocomplete-item" data-name="${s.name}">
                <span class="ac-name">${isFuzzy ? s.name : _highlightMatch(s.name, query)}</span>
                ${s.drug_class ? `<span class="ac-class">${s.drug_class}</span>` : ''}
            </li>`
        ).join('');
        acList.innerHTML = html;
        acList.style.display = 'block';

        acList.querySelectorAll('.autocomplete-item').forEach(li => {
            li.addEventListener('mousedown', (e) => {
                e.preventDefault();
                document.getElementById(inputId).value = li.dataset.name;
                _hideAc(inputId);
            });
        });
    }

    function _hideAc(inputId) {
        if (_acState[inputId]) _acState[inputId].index = -1;
        const acId = inputId.replace('cmp-drug-', 'cmp-ac-');
        const el = document.getElementById(acId);
        if (el) { el.innerHTML = ''; el.style.display = 'none'; }
    }

    function _highlightItems(items, idx) {
        items.forEach((li, i) => li.classList.toggle('ac-active', i === idx));
        if (items[idx]) items[idx].scrollIntoView({ block: 'nearest' });
    }

    function _highlightMatch(text, query) {
        const idx = text.toLowerCase().indexOf(query.toLowerCase());
        if (idx === -1) return text;
        return text.slice(0, idx) + '<strong>' + text.slice(idx, idx + query.length) + '</strong>' + text.slice(idx + query.length);
    }

    /* ── Run comparison ── */
    async function runComparison() {
        const names = [];
        for (let i = 1; i <= 4; i++) {
            const val = (document.getElementById(`cmp-drug-${i}`).value || '').trim();
            if (val) names.push(val);
        }

        if (names.length < 2) {
            document.getElementById('cmp-results').innerHTML =
                '<p class="error-msg">Please enter at least 2 drug names to compare.</p>';
            return;
        }

        const resultsEl = document.getElementById('cmp-results');
        resultsEl.innerHTML = '<div class="loading">Comparing drugs… New drugs may take a moment to retrieve from verified sources.</div>';

        // Ensure currency rates are ready
        await Currency.loadRates();

        const data = await API.compareDrugs(names);

        if (data.error) {
            resultsEl.innerHTML = `<p class="error-msg">${data.error}</p>`;
            return;
        }

        renderComparison(data, resultsEl);
    }

    /* ── Cached last comparison for re-render on currency change ── */
    let _lastData = null;
    let _lastContainer = null;

    /* ── Render comparison results ── */
    function renderComparison(data, container) {
        _lastData = data;
        _lastContainer = container;
        const drugs = data.comparison || [];
        if (!drugs.length) {
            container.innerHTML = '<p class="error-msg">No drugs found for comparison.</p>';
            return;
        }

        const colCount = drugs.length;

        // Header cards row
        let html = `<div class="cmp-header-row cmp-cols-${colCount}">`;
        drugs.forEach(d => {
            html += `<div class="cmp-drug-header-card">
                <div class="cmp-drug-name">${d.generic_name}</div>
                ${d.brand_names && d.brand_names.length
                    ? `<div class="cmp-brands">${d.brand_names.join(', ')}</div>` : ''}
                ${d.drug_class
                    ? `<span class="cmp-class-badge">${d.drug_class}</span>` : ''}
            </div>`;
        });
        html += '</div>';

        // Comparison sections (card-based, not a raw table)
        const sections = [
            { key: 'mechanism', label: 'Mechanism of Action', icon: '🧬' },
            { key: 'indications', label: 'Approved Indications', icon: '📋' },
            { key: 'dosage', label: 'Adult Dosage', icon: '💊' },
            { key: 'safety', label: 'Key Safety Warnings', icon: '⚠️' },
            { key: 'interactions', label: 'Notable Interactions', icon: '🔗' },
            { key: 'pricing', label: 'Approximate Cost', icon: '💰' },
            { key: 'source', label: 'Data Source', icon: '📄' },
        ];

        sections.forEach(sec => {
            html += `<div class="cmp-section">`;
            // Add currency selector row for pricing section
            if (sec.key === 'pricing') {
                html += `<div class="cmp-section-title-row">
                    <h3 class="cmp-section-title" style="margin-bottom:0;">${sec.icon} ${sec.label}</h3>
                    <select id="cmp-currency-select" class="currency-select">${Currency.optionsHtml()}</select>
                </div>`;
                if (Currency.locationNote() && Currency.current() !== 'USD') {
                    html += `<div class="currency-location-note" style="font-size:11px;margin:4px 0 8px;">${Currency.locationNote()}</div>`;
                }
            } else {
                html += `<h3 class="cmp-section-title">${sec.icon} ${sec.label}</h3>`;
            }
            html += `<div class="cmp-section-grid cmp-cols-${colCount}">`;
            drugs.forEach(drug => {
                html += `<div class="cmp-cell">${_formatSection(drug, sec.key)}</div>`;
            });
            html += `</div></div>`;
        });

        // Not-found notice
        if (data.not_found && data.not_found.length) {
            html += `<div class="cmp-notice warning">
                <strong>Not found in database:</strong> ${data.not_found.join(', ')}
            </div>`;
        }

        // Disclaimer
        if (data.disclaimer) {
            html += `<div class="disclaimer-banner" style="margin-top:16px;font-size:12px;">${data.disclaimer}</div>`;
        }

        container.innerHTML = html;

        // Bind currency selector
        const currSel = document.getElementById('cmp-currency-select');
        if (currSel) {
            currSel.addEventListener('change', () => {
                Currency.setCurrency(currSel.value);
                if (_lastData && _lastContainer) {
                    renderComparison(_lastData, _lastContainer);
                }
            });
        }
    }

    /* ── Format each comparison cell ── */
    function _formatSection(drug, key) {
        switch (key) {
            case 'mechanism':
                return drug.mechanism_of_action
                    ? `<p>${_truncate(drug.mechanism_of_action, 400)}</p>`
                    : '<span class="cmp-na">N/A</span>';

            case 'indications':
                if (!drug.indications || !drug.indications.length) return '<span class="cmp-na">N/A</span>';
                return '<ul class="cmp-bullets">' +
                    drug.indications.map(i =>
                        `<li>${_truncate(i.approved_use, 150)}</li>`
                    ).join('') + '</ul>';

            case 'dosage':
                if (!drug.dosage_guidelines || !drug.dosage_guidelines.length) return '<span class="cmp-na">N/A</span>';
                return drug.dosage_guidelines.map(d =>
                    d.adult_dosage ? `<p>${_truncate(d.adult_dosage, 300)}</p>` : ''
                ).join('') || '<span class="cmp-na">N/A</span>';

            case 'safety': {
                if (!drug.safety_warnings || !drug.safety_warnings.length) return '<span class="cmp-na">N/A</span>';
                let h = '';
                drug.safety_warnings.forEach(w => {
                    if (w.black_box_warnings) {
                        h += `<div class="cmp-blackbox">⛔ ${_truncate(w.black_box_warnings, 200)}</div>`;
                    }
                    if (w.contraindications) {
                        h += `<p><strong>Contraindications:</strong> ${_truncate(w.contraindications, 200)}</p>`;
                    }
                    if (w.pregnancy_risk) {
                        h += `<p><strong>Pregnancy:</strong> ${_truncate(w.pregnancy_risk, 100)}</p>`;
                    }
                    // FAERS summary
                    if (w.adverse_event_count) {
                        const serious = w.adverse_event_serious_count || 0;
                        const pct = w.adverse_event_count ? ((serious / w.adverse_event_count) * 100).toFixed(1) : '—';
                        h += `<div class="cmp-faers">
                            FAERS: ${w.adverse_event_count.toLocaleString()} reports
                            (${pct}% serious)
                        </div>`;
                    }
                });
                return h || '<span class="cmp-na">N/A</span>';
            }

            case 'interactions':
                if (!drug.interactions || !drug.interactions.length) return '<span class="cmp-na">None documented</span>';
                return drug.interactions.slice(0, 4).map(ix => {
                    const sevColors = {
                        'contraindicated': '#e74c3c', 'major': '#e67e22',
                        'moderate': '#f1c40f', 'minor': '#27ae60',
                    };
                    const col = sevColors[ix.severity] || '#888';
                    return `<div class="cmp-interaction">
                        <span>${ix.interacting_drug}</span>
                        <span class="cmp-sev-badge" style="background:${col};">${ix.severity}</span>
                    </div>`;
                }).join('');

            case 'pricing':
                if (!drug.pricing || !drug.pricing.length) return '<span class="cmp-na">No data</span>';
                return drug.pricing.map(p => {
                    let txt = '';
                    const isNadac = p.pricing_source === 'NADAC';
                    const tag = isNadac
                        ? '<span class="cmp-price-tag nadac">CMS NADAC</span>'
                        : '<span class="cmp-price-tag est">Estimate</span>';
                    txt += tag;
                    if (isNadac && p.nadac_per_unit) {
                        txt += `<div class="cmp-price-val">${Currency.format(p.nadac_per_unit, 4)}/unit</div>`;
                        if (Currency.current() !== 'USD') {
                            txt += `<div style="font-size:10px;color:var(--text-muted);">(US$${p.nadac_per_unit.toFixed(4)})</div>`;
                        }
                    }
                    if (p.approximate_cost) {
                        // Parse unit cost from approximate_cost and convert
                        const unitMatch = p.approximate_cost.match(/\$(\d+\.\d+)\/EA/);
                        const monthlyMatch = p.approximate_cost.match(/~\$(\d[\d.,]*)[\u2013-]\$(\d[\d.,]*)\/month/);
                        if (unitMatch) {
                            txt += `<div class="cmp-price-cost">Unit: ${Currency.format(parseFloat(unitMatch[1]), 4)}/ea</div>`;
                        }
                        if (monthlyMatch) {
                            const lo = parseFloat(monthlyMatch[1].replace(',', ''));
                            const hi = parseFloat(monthlyMatch[2].replace(',', ''));
                            txt += `<div class="cmp-price-cost">Monthly: ${Currency.format(lo)} – ${Currency.format(hi)}</div>`;
                        }
                        if (!unitMatch && !monthlyMatch) {
                            const first = p.approximate_cost.split(';')[0].trim();
                            txt += `<div class="cmp-price-cost">${_truncate(first, 120)}</div>`;
                        }
                    }
                    return `<div class="cmp-pricing-entry">${txt}</div>`;
                }).join('');

            case 'source':
                if (!drug.source) return '<span class="cmp-na">N/A</span>';
                const s = drug.source;
                const authority = s.authority || '';
                const badgeColors = { 'FDA': '#1a5276', 'NIH/NLM': '#196f3d', 'CMS': '#7d3c98' };
                const color = badgeColors[authority] || '#555';
                return `<div>
                    <span class="cmp-auth-badge" style="background:${color};">${authority}</span>
                    <span class="cmp-src-title">${s.document_title || ''} ${s.publication_year ? '(' + s.publication_year + ')' : ''}</span>
                    ${s.url ? `<br><a href="${s.url}" target="_blank" rel="noopener" class="cmp-verify-link">Verify ↗</a>` : ''}
                </div>`;

            default:
                return drug[key] || '<span class="cmp-na">N/A</span>';
        }
    }

    function _truncate(str, max) {
        if (!str) return '';
        return str.length > max ? str.substring(0, max) + '…' : str;
    }

    return { render };
})();
