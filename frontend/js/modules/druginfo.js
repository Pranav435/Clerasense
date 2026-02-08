/**
 * Clerasense – Drug Information Module
 * Displays comprehensive drug profiles with pricing, safety,
 * dosage, and interaction data from verified regulatory sources.
 * This is a LOOKUP page, not a chat interface.
 */

const DrugInfoModule = (() => {

    /* ── Currency helpers (delegated to shared Currency utility) ── */
    function _formatPrice(usd, decimals = 2) {
        return Currency.format(usd, decimals);
    }

    /**
     * Parse an approximate_cost string like "₹50.55 strip of 10 tablet ir"
     * or "₹50.55 (strip of 10 tablets)" to extract pack price and pack count.
     * Returns { price: number, count: number, currency: '₹'|'$', label: string } or null.
     */
    function _parsePackPrice(approxCost) {
        if (!approxCost) return null;
        // Match currency + price
        const m = approxCost.match(/([₹$])\s*(\d+(?:\.\d+)?)/);
        if (!m) return null;
        const currency = m[1];
        const price = parseFloat(m[2]);
        if (isNaN(price) || price <= 0) return null;
        // Try to extract pack count: "strip of 10", "pack of 15", "bottle of 100"
        const cm = approxCost.match(/(?:strip|pack|bottle|box|vial|tube|sachet|bag)\s*(?:of\s+)?(\d+)/i);
        const count = cm ? parseInt(cm[1], 10) : 0;
        return { price, count: count > 0 ? count : 1, currency, label: approxCost };
    }

    function render(container) {
        container.innerHTML = `
            <div class="druginfo-container">
                <div class="chat-header">
                    <h2>Drug Information</h2>
                    <p>Look up comprehensive, source-verified drug profiles including indications,
                       dosages, safety warnings, interactions, and pricing.</p>
                </div>
                <div class="disclaimer-banner">
                    ⚠️ Information sourced from FDA, NIH/NLM, CMS NADAC, and FDA FAERS.
                    This is an information tool only — NOT a substitute for clinical judgment.
                </div>
                <div class="druginfo-search">
                    <div class="form-group" style="flex:1;margin-bottom:0;position:relative;">
                        <label>Drug Name</label>
                        <input type="text" id="druginfo-input"
                               placeholder="e.g., Metformin, Atorvastatin, Lisinopril"
                               autocomplete="off">
                        <ul id="druginfo-autocomplete" class="autocomplete-list"></ul>
                    </div>
                    <button id="druginfo-search-btn" class="btn btn-primary"
                            style="width:auto;align-self:flex-end;height:42px;">
                        Look Up
                    </button>
                </div>
                <div id="druginfo-results"></div>
            </div>
        `;

        const input = document.getElementById('druginfo-input');
        const btn = document.getElementById('druginfo-search-btn');
        const acList = document.getElementById('druginfo-autocomplete');

        btn.addEventListener('click', () => { hideAutocomplete(); lookupDrug(); });
        input.addEventListener('keydown', (e) => {
            const items = document.querySelectorAll('#druginfo-autocomplete .autocomplete-item');
            const visible = items.length > 0 && document.getElementById('druginfo-autocomplete').style.display !== 'none';

            if (e.key === 'ArrowDown' && visible) {
                e.preventDefault();
                _acIndex = Math.min(_acIndex + 1, items.length - 1);
                _highlightAcItem(items);
            } else if (e.key === 'ArrowUp' && visible) {
                e.preventDefault();
                _acIndex = Math.max(_acIndex - 1, 0);
                _highlightAcItem(items);
            } else if (e.key === 'Enter') {
                if (visible && _acIndex >= 0 && items[_acIndex]) {
                    e.preventDefault();
                    input.value = items[_acIndex].dataset.name;
                    hideAutocomplete();
                    lookupDrug();
                } else {
                    hideAutocomplete();
                    lookupDrug();
                }
            } else if (e.key === 'Escape') {
                hideAutocomplete();
            }
        });

        // Typeahead
        let _acTimer = null;
        input.addEventListener('input', () => {
            clearTimeout(_acTimer);
            _acIndex = -1;
            const q = input.value.trim();
            if (q.length < 2) { hideAutocomplete(); return; }
            _acTimer = setTimeout(() => fetchSuggestions(q), 220);
        });

        // Close autocomplete on outside click
        document.addEventListener('click', (e) => {
            if (!e.target.closest('.form-group')) hideAutocomplete();
        });
    }

    let _acIndex = -1;

    function hideAutocomplete() {
        _acIndex = -1;
        const el = document.getElementById('druginfo-autocomplete');
        if (el) { el.innerHTML = ''; el.style.display = 'none'; }
    }

    function _highlightAcItem(items) {
        items.forEach((li, i) => {
            li.classList.toggle('ac-active', i === _acIndex);
        });
        if (items[_acIndex]) {
            items[_acIndex].scrollIntoView({ block: 'nearest' });
        }
    }

    async function fetchSuggestions(query) {
        const res = await API.autocompleteDrugs(query);
        const list = (res && res.suggestions) || [];
        const isFuzzy = res && res.fuzzy;
        const acList = document.getElementById('druginfo-autocomplete');
        if (!acList) return;

        if (!list.length) { hideAutocomplete(); return; }

        let html = '';
        if (isFuzzy) {
            html += `<li class="autocomplete-hint">Did you mean…</li>`;
        }
        html += list.map(s =>
            `<li class="autocomplete-item" data-name="${s.name}">
                <span class="ac-name">${isFuzzy ? s.name : highlightMatch(s.name, query)}</span>
                ${s.drug_class ? `<span class="ac-class">${s.drug_class}</span>` : ''}
            </li>`
        ).join('');
        acList.innerHTML = html;
        acList.style.display = 'block';

        // Click handler for each suggestion
        acList.querySelectorAll('.autocomplete-item').forEach(li => {
            li.addEventListener('mousedown', (e) => {
                e.preventDefault(); // prevent input blur
                const name = li.dataset.name;
                document.getElementById('druginfo-input').value = name;
                hideAutocomplete();
                lookupDrug();
            });
        });
    }

    function highlightMatch(text, query) {
        const idx = text.toLowerCase().indexOf(query.toLowerCase());
        if (idx === -1) return text;
        const before = text.slice(0, idx);
        const match = text.slice(idx, idx + query.length);
        const after = text.slice(idx + query.length);
        return `${before}<strong>${match}</strong>${after}`;
    }

    async function lookupDrug() {
        const name = document.getElementById('druginfo-input').value.trim();
        if (!name) {
            document.getElementById('druginfo-results').innerHTML =
                '<p class="error-msg">Please enter a drug name.</p>';
            return;
        }

        const resultsEl = document.getElementById('druginfo-results');
        resultsEl.innerHTML = '<div class="loading">Retrieving drug profile from FDA, DailyMed, NADAC &amp; FAERS… may take a moment for new drugs.</div>';

        // Ensure rates are loaded
        await Currency.loadRates();

        // Fetch drug profile AND pricing in parallel
        const country = App.getUserCountry() || 'US';
        const [rawDrug, pricingData] = await Promise.all([
            API.getDrugByName(name),
            API.getPricing(name, country),
        ]);

        if (rawDrug.error) {
            // Drug not found — try fuzzy suggestions
            const fuzzy = await API.suggestDrugs(name);
            const suggestions = (fuzzy && fuzzy.suggestions) || [];
            if (suggestions.length) {
                const pills = suggestions.map(s =>
                    `<button class="suggest-pill" data-name="${s.name}">
                        ${s.name}${s.drug_class ? ` <span class="suggest-class">(${s.drug_class})</span>` : ''}
                    </button>`
                ).join('');
                resultsEl.innerHTML = `
                    <div class="druginfo-suggest-box">
                        <p class="error-msg" style="margin-bottom:10px;">No exact match found for "<strong>${name}</strong>".</p>
                        <p class="suggest-label">Did you mean:</p>
                        <div class="suggest-pills">${pills}</div>
                    </div>`;
                // Bind click handlers
                resultsEl.querySelectorAll('.suggest-pill').forEach(btn => {
                    btn.addEventListener('click', () => {
                        document.getElementById('druginfo-input').value = btn.dataset.name;
                        lookupDrug();
                    });
                });
            } else {
                resultsEl.innerHTML = `<p class="error-msg">${rawDrug.error}</p>`;
            }
            return;
        }

        // Unwrap the { drug: { ... } } envelope
        const drug = rawDrug.drug || rawDrug;

        renderDrugProfile(drug, pricingData, resultsEl);
        updateContextPanel(drug);

        // Load brands asynchronously (after main profile renders)
        loadBrandsPanel(drug);
    }

    /* ── Source badge (reusable) ── */
    function renderSourceBadge(source, extraLabel) {
        if (!source) return '';
        const authority = source.authority || 'Unknown';
        const badgeColors = { 'FDA': '#1a5276', 'NIH/NLM': '#196f3d', 'CMS': '#7d3c98' };
        const color = badgeColors[authority] || '#555';
        const title = source.document_title || '';
        const year = source.publication_year || '';
        const url = source.url || '';

        return `<div class="source-badge-row">
            <span class="authority-badge" style="background:${color};">${authority}</span>
            ${extraLabel ? `<span class="authority-badge" style="background:#2e7d32;">${extraLabel}</span>` : ''}
            <span>${title}${year ? ' (' + year + ')' : ''}</span>
            ${url ? ` <a href="${url}" target="_blank" rel="noopener" style="color:${color};margin-left:6px;">Verify ↗</a>` : ''}
        </div>`;
    }

    /* ── Main drug profile renderer ── */
    function renderDrugProfile(drug, pricing, container) {
        _expandId = 0;  // reset for fresh IDs on re-render
        let html = '';

        // ── Header Card ──
        html += `<div class="druginfo-card druginfo-header-card">
            <div class="druginfo-title-row">
                <div>
                    <h2 class="druginfo-drug-name">${drug.generic_name || 'Unknown'}</h2>
                    ${drug.brand_names && drug.brand_names.length
                        ? `<div class="druginfo-brands">Brand: ${drug.brand_names.join(', ')}</div>` : ''}
                </div>
                ${drug.drug_class
                    ? `<span class="druginfo-class-badge">${drug.drug_class}</span>` : ''}
            </div>
            ${drug.mechanism_of_action
                ? `<div class="druginfo-mechanism">
                       <strong>Mechanism of Action:</strong>
                       ${formatText(drug.mechanism_of_action)}
                   </div>` : ''}
            ${renderSourceBadge(drug.source)}
        </div>`;

        // ── Indications (deduplicated) ──
        if (drug.indications && drug.indications.length) {
            // Deduplicate overlapping indications
            const seenInd = new Set();
            const uniqueInd = drug.indications.filter(ind => {
                const key = (ind.approved_use || '').toLowerCase().replace(/[^a-z0-9]/g, '').slice(0, 80);
                if (seenInd.has(key)) return false;
                seenInd.add(key);
                return true;
            });
            html += `<div class="druginfo-card">
                <h3 class="druginfo-section-title">📋 Approved Indications</h3>`;
            uniqueInd.forEach(ind => {
                html += `<div class="druginfo-item">
                    ${formatText(ind.approved_use)}
                    ${renderSourceBadge(ind.source)}
                </div>`;
            });
            html += `</div>`;
        }

        // ── Dosage Guidelines ──
        if (drug.dosage_guidelines && drug.dosage_guidelines.length) {
            html += `<div class="druginfo-card">
                <h3 class="druginfo-section-title">💊 Dosage Guidelines</h3>`;
            drug.dosage_guidelines.forEach(d => {
                html += `<div class="druginfo-dosage-grid">`;
                if (d.adult_dosage) {
                    html += `<div class="druginfo-dosage-cell">
                        <div class="dosage-label">Adult Dosage</div>
                        <div class="dosage-value">${formatText(d.adult_dosage)}</div>
                    </div>`;
                }
                if (d.pediatric_dosage) {
                    html += `<div class="druginfo-dosage-cell">
                        <div class="dosage-label">Pediatric Dosage</div>
                        <div class="dosage-value">${formatText(d.pediatric_dosage)}</div>
                    </div>`;
                }
                if (d.renal_adjustment) {
                    html += `<div class="druginfo-dosage-cell">
                        <div class="dosage-label">Renal Adjustment</div>
                        <div class="dosage-value">${formatText(d.renal_adjustment)}</div>
                    </div>`;
                }
                if (d.hepatic_adjustment) {
                    html += `<div class="druginfo-dosage-cell">
                        <div class="dosage-label">Hepatic Adjustment</div>
                        <div class="dosage-value">${formatText(d.hepatic_adjustment)}</div>
                    </div>`;
                }
                html += `</div>`;

                // ── Overdose & Underdose Information ──
                if (d.overdose_info || d.underdose_info) {
                    html += `<div class="druginfo-dose-safety">`;
                    if (d.overdose_info) {
                        html += `<div class="druginfo-overdose">
                            <div class="dose-safety-header overdose-header">🔴 Overdose Information</div>
                            <div class="dose-safety-body">${formatText(d.overdose_info)}</div>
                        </div>`;
                    }
                    if (d.underdose_info) {
                        html += `<div class="druginfo-underdose">
                            <div class="dose-safety-header underdose-header">🟡 Underdose / Missed Dose</div>
                            <div class="dose-safety-body">${formatText(d.underdose_info)}</div>
                        </div>`;
                    }
                    html += `</div>`;
                }

                html += renderSourceBadge(d.source);
            });
            html += `</div>`;
        }

        // ── Safety Warnings ──
        if (drug.safety_warnings && drug.safety_warnings.length) {
            html += `<div class="druginfo-card">
                <h3 class="druginfo-section-title">⚠️ Safety Warnings</h3>`;
            drug.safety_warnings.forEach(w => {
                if (w.black_box_warnings) {
                    html += `<div class="druginfo-blackbox">
                        <strong>⛔ BLACK BOX WARNING</strong>
                        ${formatText(w.black_box_warnings)}
                    </div>`;
                }
                if (w.contraindications) {
                    html += `<div class="druginfo-item">
                        <strong>🚫 Contraindications:</strong>
                        ${formatText(w.contraindications)}
                    </div>`;
                }
                if (w.pregnancy_risk) {
                    html += `<div class="druginfo-item">
                        <strong>🤰 Pregnancy:</strong>
                        ${formatText(w.pregnancy_risk)}
                    </div>`;
                }
                if (w.lactation_risk) {
                    html += `<div class="druginfo-item">
                        <strong>🍼 Lactation:</strong>
                        ${formatText(w.lactation_risk)}
                    </div>`;
                }
                html += renderAdverseEvents(w);
                html += renderSourceBadge(w.source);
            });
            html += `</div>`;
        }

        // ── Drug Interactions ──
        if (drug.interactions && drug.interactions.length) {
            html += `<div class="druginfo-card">
                <h3 class="druginfo-section-title">🔗 Drug Interactions</h3>
                <div class="druginfo-interactions-list">`;
            drug.interactions.forEach(ix => {
                const sevColors = {
                    'contraindicated': '#e74c3c', 'major': '#e67e22',
                    'moderate': '#f1c40f', 'minor': '#27ae60',
                };
                const sevColor = sevColors[ix.severity] || '#888';
                html += `<div class="druginfo-interaction-row">
                    <span class="interaction-drug">${sentenceCase(ix.interacting_drug)}</span>
                    <span class="interaction-severity" style="background:${sevColor};">${sentenceCase(ix.severity)}</span>
                    <span class="interaction-desc">${sentenceCase(ix.description || '')}</span>
                </div>`;
            });
            html += `</div></div>`;
        }

        // ── Pricing & Reimbursement ──
        html += renderPricingSection(pricing);

        // ── Brands Panel (placeholder – loaded asynchronously) ──
        html += `<div id="brands-section-card" class="druginfo-card">
            <h3 class="druginfo-section-title">🏭 Brand Products</h3>
            <div id="brands-loading" class="loading" style="font-size:13px;">Loading brand product data from FDA &amp; NADAC…</div>
        </div>`;

        container.innerHTML = html;

        // Bind currency selector change handler
        const sel = document.getElementById('currency-select');
        if (sel) {
            sel.addEventListener('change', () => {
                Currency.setCurrency(sel.value);
                // Re-render pricing section only
                const pricingCard = document.getElementById('pricing-section-card');
                if (pricingCard) {
                    pricingCard.outerHTML = renderPricingSection(pricing);
                    bindCurrencySelector(pricing);
                }
            });
        }
    }

    function bindCurrencySelector(pricing) {
        const sel = document.getElementById('currency-select');
        if (!sel) return;
        sel.addEventListener('change', () => {
            Currency.setCurrency(sel.value);
            const pc = document.getElementById('pricing-section-card');
            if (pc) {
                pc.outerHTML = renderPricingSection(pricing);
                bindCurrencySelector(pricing);
            }
        });
    }

    /* ── Adverse events (FAERS) ── */
    function renderAdverseEvents(warning) {
        const count = warning.adverse_event_count;
        const serious = warning.adverse_event_serious_count;
        const reactions = warning.top_adverse_reactions || [];
        if (!count && !reactions.length) return '';

        let html = '<div class="druginfo-faers">';
        html += '<strong>📊 FDA Adverse Event Reports (FAERS)</strong>';

        if (count) {
            const seriousPct = serious && count ? ((serious / count) * 100).toFixed(1) : '—';
            html += `<div class="faers-stats">
                <div class="faers-stat">
                    <div class="faers-stat-num" style="color:#e67e22;">${count.toLocaleString()}</div>
                    <div class="faers-stat-label">Total Reports</div>
                </div>
                <div class="faers-stat">
                    <div class="faers-stat-num" style="color:#c0392b;">${serious ? serious.toLocaleString() : '—'}</div>
                    <div class="faers-stat-label">Serious</div>
                </div>
                <div class="faers-stat">
                    <div class="faers-stat-num" style="color:#c0392b;">${seriousPct}%</div>
                    <div class="faers-stat-label">Serious Rate</div>
                </div>
            </div>`;
        }

        if (reactions.length) {
            html += '<div class="faers-reactions"><strong>Top Reported Reactions:</strong><ul>';
            for (const r of reactions.slice(0, 8)) {
                html += `<li>${r.reaction} <span style="color:#888;">(${r.count.toLocaleString()})</span></li>`;
            }
            html += '</ul></div>';
        }

        html += `<div class="faers-footer">Source: <a href="https://open.fda.gov/apis/drug/event/" target="_blank" rel="noopener">FDA FAERS</a></div>`;
        html += '</div>';
        return html;
    }

    /* ── Simplified Pricing section ── */
    function renderPricingSection(data) {
        // Build currency option list
        const currencyOptions = Currency.optionsHtml();

        if (!data || data.error) {
            return `<div class="druginfo-card" id="pricing-section-card">
                <div class="druginfo-section-title-row">
                    <h3 class="druginfo-section-title" style="margin-bottom:0;">💰 Pricing & Reimbursement</h3>
                    <select id="currency-select" class="currency-select">${currencyOptions}</select>
                </div>
                <p style="color:var(--text-muted);font-size:13px;margin-top:12px;">Pricing data not available.</p>
            </div>`;
        }

        let html = `<div class="druginfo-card" id="pricing-section-card">
            <div class="druginfo-section-title-row">
                <h3 class="druginfo-section-title" style="margin-bottom:0;">💰 Pricing & Reimbursement</h3>
                <select id="currency-select" class="currency-select">${currencyOptions}</select>
            </div>`;

        // Location note
        if (Currency.locationNote() && Currency.current() !== 'USD') {
            html += `<div class="currency-location-note">${Currency.locationNote()}</div>`;
        }

        // Generic availability
        html += `<div style="margin:12px 0 8px;">
            ${data.generic_available
                ? '<span class="generic-badge">✅ Generic Available</span>'
                : '<span class="generic-badge" style="background:#fef2f2;color:var(--danger);">Brand Only</span>'}
        </div>`;

        // Pricing entries — parse compound cost string into per-formulation rows
        if (data.pricing && data.pricing.length) {
            data.pricing.forEach(p => {
                const isNadac = p.pricing_source === 'NADAC';
                const sourceLabel = isNadac ? 'NADAC (Government Pharmacy Acquisition Cost)' : 'Estimated Retail Price';

                html += `<div class="druginfo-pricing-entry ${isNadac ? 'nadac' : 'estimate'}">`;
                html += `<div class="pricing-source-header">
                    <span class="pricing-tag ${isNadac ? 'govt' : 'est'}">${sourceLabel}</span>
                </div>`;

                // Parse formulation rows from approximate_cost
                if (p.approximate_cost) {
                    const segments = p.approximate_cost.split(';').map(s => s.trim()).filter(Boolean);
                    if (segments.length > 1) {
                        // Multiple formulations — show each labeled separately
                        html += '<div class="pricing-formulations">';
                        segments.forEach(seg => {
                            // Format: "$0.70/EA → ~$21–$63/month (FORMULATION NAME)"
                            const nameMatch = seg.match(/\(([^)]+)\)/);
                            const formName = nameMatch ? nameMatch[1] : 'Standard';
                            // Extract unit cost and monthly range
                            const unitMatch = seg.match(/^\$([\d.]+)\/EA/);
                            const monthlyMatch = seg.match(/~\$([\d.,]+)[–-]\$([\d.,]+)\/month/);
                            html += `<div class="pricing-formulation-row">
                                <div class="formulation-name">${formName}</div>
                                <div class="formulation-costs">`;
                            if (unitMatch) {
                                html += `<span class="formulation-unit">Unit: <strong>${_formatPrice(parseFloat(unitMatch[1]), 4)}</strong>/ea</span>`;
                            }
                            if (monthlyMatch) {
                                html += `<span class="formulation-monthly">Monthly (30–90 day): <strong>${_formatPrice(parseFloat(monthlyMatch[1].replace(',','')))}</strong> – <strong>${_formatPrice(parseFloat(monthlyMatch[2].replace(',','')))}</strong></span>`;
                            }
                            html += `</div></div>`;
                        });
                        html += '</div>';
                    } else {
                        // Single price — show simply
                        const seg = segments[0];
                        const nameMatch = seg.match(/\(([^)]+)\)/);
                        const formName = nameMatch ? nameMatch[1] : (p.nadac_package_description || '');
                        html += `<div class="pricing-single">
                            ${formName ? `<div class="formulation-name">${formName}</div>` : ''}
                            <div class="pricing-main-cost">${seg.replace(/\([^)]+\)/, '').trim()}</div>
                        </div>`;
                    }
                } else {
                    html += '<p style="color:var(--text-muted);font-size:13px;">Cost data not available for this entry.</p>';
                }

                // NADAC unit price (converted)
                if (isNadac && p.nadac_per_unit) {
                    html += `<div class="pricing-unit-row">
                        Verified unit cost: <strong>${_formatPrice(p.nadac_per_unit, 4)}</strong>/unit
                        ${Currency.current() !== 'USD' ? `<span class="pricing-orig">(US$${p.nadac_per_unit.toFixed(4)})</span>` : ''}
                        ${p.nadac_effective_date ? `<span class="pricing-date">as of ${p.nadac_effective_date}</span>` : ''}
                    </div>`;
                }

                html += renderSourceBadge(p.source, isNadac ? 'NADAC' : null);
                html += `</div>`;
            });
        } else {
            html += '<p style="color:var(--text-muted);font-size:13px;">No verified pricing data available.</p>';
        }

        // Reimbursement – country-specific government schemes
        if (data.reimbursement && data.reimbursement.length) {
            const countryLabel = data.reimbursement_country || 'your country';
            html += `<h4 class="druginfo-subsection-title">🏛️ Government Reimbursement Schemes</h4>`;
            html += `<div class="reimb-country-note">Showing schemes for <strong>${countryLabel}</strong> (based on your location)</div>`;
            data.reimbursement.forEach(r => {
                const statusCls = r.coverage_status === 'likely_covered' ? 'reimb-likely'
                                : r.coverage_status === 'may_be_covered' ? 'reimb-maybe'
                                : r.coverage_status === 'inpatient_only' ? 'reimb-inpatient'
                                : 'reimb-check';
                const statusLabel = r.coverage_status === 'likely_covered' ? '✅ Likely Covered'
                                  : r.coverage_status === 'may_be_covered' ? '🟡 May Be Covered'
                                  : r.coverage_status === 'inpatient_only' ? '🏥 Inpatient Only'
                                  : '🔍 Check Formulary';
                html += `<div class="reimb-card ${statusCls}">
                    <div class="reimb-header">
                        <div class="reimb-scheme-name">${r.scheme_name}</div>
                        <span class="reimb-status-chip ${statusCls}">${statusLabel}</span>
                    </div>
                    <p class="reimb-desc">${r.description}</p>`;
                if (r.coverage_note) {
                    html += `<div class="reimb-row"><span class="reimb-label">Drug Note</span><span>${r.coverage_note}</span></div>`;
                }
                if (r.eligibility) {
                    html += `<div class="reimb-row"><span class="reimb-label">Eligibility</span><span>${r.eligibility}</span></div>`;
                }
                if (r.how_to_access) {
                    html += `<div class="reimb-row"><span class="reimb-label">How to Access</span><span>${r.how_to_access}</span></div>`;
                }
                html += renderSourceBadge(r.source);
                html += `</div>`;
            });
        }

        if (data.disclaimer) {
            html += `<div class="disclaimer-banner" style="margin-top:12px;font-size:11px;">${data.disclaimer}</div>`;
        }

        html += `</div>`;
        return html;
    }

    function truncate(str, max) {
        if (!str) return '';
        // Strip black squares and block chars
        const clean = str.replace(/[■▪▐▓░▒█▬▮▯◼◾⬛⬜□▢]/g, '');
        return clean.length > max ? clean.substring(0, max) + '…' : clean;
    }

    /**
     * Apply sentence case: capitalize first letter of each sentence/bullet,
     * preserving ALL-CAPS words, proper nouns, and abbreviations.
     */
    function sentenceCase(text) {
        if (!text) return '';
        // Strip black squares and block chars
        let result = text.replace(/[■▪▐▓░▒█▬▮▯◼◾⬛⬜□▢]/g, '');
        // Capitalize the very first character
        result = result.replace(/^\s*([a-z])/, (_, c) => c.toUpperCase());
        // Capitalize after sentence-ending punctuation followed by space
        result = result.replace(/([.!?:;])\s+([a-z])/g, (_, p, c) => p + ' ' + c.toUpperCase());
        // Capitalize after bullet dash or colon at start of line
        result = result.replace(/(^|\n)\s*[-–—]\s*([a-z])/g, (_, pre, c) => pre + '- ' + c.toUpperCase());
        return result;
    }

    let _expandId = 0;

    /**
     * Format a long medical text blob into readable bullet-pointed HTML.
     * Splits on sentence boundaries, numbered lists, semicolons, and bullet chars;
     * deduplicates; applies sentence case; wraps in <ul>.
     * For very long content, shows a preview with "Read more" toggle.
     */
    function formatText(raw) {
        if (!raw) return '';
        // Strip black squares, block chars, and other visual artifacts
        let text = raw.replace(/[■▪▐▓░▒█▬▮▯◼◾⬛⬜□▢■]/g, '').trim();

        // Normalise various separators
        let parts = text
            .split(/(?<=[.;])\s+|\s*[•●▪►\-–—]\s+|\s*\n\s*|\s*(?=\(\d+\)\s)|\s*(?=\d+\.\s)/)
            .map(s => s.trim())
            .map(s => s.replace(/^\(\s*\d+\s*\)\s*/, '').replace(/^\d+\.\s*/, '').replace(/^[-–—]\s*/, ''))
            .map(s => s.trim())
            .filter(s => s.length > 5);

        // Deduplicate (some data has repeated sentences)
        const seen = new Set();
        parts = parts.filter(p => {
            const key = p.toLowerCase().replace(/[^a-z0-9]/g, '').slice(0, 60);
            if (seen.has(key)) return false;
            seen.add(key);
            return true;
        });

        // Apply sentence case to each part
        parts = parts.map(p => sentenceCase(p));

        let fullHtml;

        // If 1 short item, just return as paragraph
        if (parts.length <= 1 && text.length < 150) {
            return `<p>${sentenceCase(text)}</p>`;
        }

        if (parts.length <= 1) {
            const commaParts = text.split(/,\s*/)
                .map(s => s.trim())
                .filter(s => s.length > 5);
            if (commaParts.length >= 3) {
                parts = commaParts.map(p => sentenceCase(p));
                fullHtml = '<ul class="druginfo-bullets">' +
                    parts.map(p => `<li>${p}</li>`).join('') +
                    '</ul>';
            } else {
                fullHtml = `<p>${sentenceCase(text)}</p>`;
            }
        } else {
            fullHtml = '<ul class="druginfo-bullets">' +
                parts.map(p => `<li>${p}</li>`).join('') +
                '</ul>';
        }

        // If short enough, no need for expand/collapse
        if (text.length <= 350 && parts.length <= 4) {
            return fullHtml;
        }

        // Build a preview: first 3 bullets or first 300 chars of paragraph
        let previewHtml;
        if (parts.length > 3) {
            previewHtml = '<ul class="druginfo-bullets">' +
                parts.slice(0, 3).map(p => `<li>${p}</li>`).join('') +
                '</ul>';
        } else {
            // Single long paragraph — show first ~300 chars
            const previewText = sentenceCase(text).substring(0, 300) + '…';
            previewHtml = `<p>${previewText}</p>`;
        }

        const id = 'exp-di-' + (++_expandId);
        return `<div class="text-expandable" id="${id}">
            <div class="text-preview">${previewHtml}</div>
            <div class="text-full" style="display:none;">${fullHtml}</div>
            <button class="read-more-toggle" onclick="(function(el){var p=el.closest('.text-expandable');p.querySelector('.text-preview').style.display=p.querySelector('.text-preview').style.display==='none'?'':'none';p.querySelector('.text-full').style.display=p.querySelector('.text-full').style.display==='none'?'':'none';el.textContent=el.textContent==='Read more'?'Show less':'Read more';})(this)">Read more</button>
        </div>`;
    }

    function updateContextPanel(drug) {
        const panel = document.getElementById('panel-sources');
        if (!panel) return;

        const sources = [];
        if (drug.source) sources.push(drug.source);
        (drug.indications || []).forEach(i => { if (i.source) sources.push(i.source); });
        (drug.dosage_guidelines || []).forEach(d => { if (d.source) sources.push(d.source); });
        (drug.safety_warnings || []).forEach(s => { if (s.source) sources.push(s.source); });

        const seen = new Set();
        const unique = sources.filter(s => {
            if (seen.has(s.source_id)) return false;
            seen.add(s.source_id);
            return true;
        });

        if (!unique.length) {
            panel.innerHTML = '<p class="placeholder">No sources.</p>';
            return;
        }

        panel.innerHTML = unique.map(s => `
            <div style="margin-bottom:10px;">
                <div style="font-weight:600;font-size:12px;">${s.authority}</div>
                <div style="font-size:12px;color:var(--text-secondary);">${s.document_title}</div>
                <div style="font-size:11px;color:var(--text-muted);">${s.publication_year || ''}</div>
                ${s.url ? `<a href="${s.url}" target="_blank" rel="noopener" class="source-link">View source ↗</a>` : ''}
            </div>
        `).join('');
    }

    /* ── Brands Panel ── */

    let _brandsData = [];   // cached brand list for the current drug
    let _currentDrugId = null;

    async function loadBrandsPanel(drug) {
        _currentDrugId = drug.id;
        const card = document.getElementById('brands-section-card');
        if (!card) return;

        const userCountry = App.getUserCountry();
        const userCountryName = App.getUserCountryName();
        const isUS = (userCountry === 'US');

        try {
            let localBrands = [], usBrands = [];

            if (isUS) {
                // US user → single fetch
                const res = await API.getDrugBrands(drug.id, 'US');
                usBrands = (res && res.brands) || [];
            } else {
                // Non-US user → parallel fetch: local market + US
                const [localRes, usRes] = await Promise.all([
                    API.getDrugBrands(drug.id, userCountry),
                    API.getDrugBrands(drug.id, 'US'),
                ]);
                localBrands = (localRes && localRes.brands) || [];
                usBrands = (usRes && usRes.brands) || [];
            }

            // Group brands by name to consolidate dosages
            localBrands = _groupBrands(localBrands);
            usBrands = _groupBrands(usBrands);

            // Unified flat array (local brands first, then US) — indices stay unique
            _brandsData = [...localBrands, ...usBrands];

            if (!_brandsData.length) {
                card.innerHTML = `
                    <h3 class="druginfo-section-title">🏭 Brand Products</h3>
                    <p style="color:var(--text-muted);font-size:13px;">No brand-level product data available.</p>`;
                return;
            }

            let html = `
                <div class="brands-header-row">
                    <h3 class="druginfo-section-title" style="margin-bottom:0;">🏭 Brand Products</h3>
                    <button id="compare-brands-btn" class="btn btn-small btn-outline" disabled>
                        ⚖️ Compare Selected
                    </button>
                </div>`;

            // ── Tabs (only for non-US users with local brands) ──
            if (!isUS && localBrands.length) {
                html += `
                <div class="brand-market-tabs">
                    <button class="brand-tab active" data-tab="local">
                        🌍 ${userCountryName} <span class="brand-tab-count">${localBrands.length}</span>
                    </button>
                    <button class="brand-tab" data-tab="us">
                        🇺🇸 US FDA <span class="brand-tab-count">${usBrands.length}</span>
                    </button>
                </div>`;
            } else if (!isUS && !localBrands.length && usBrands.length) {
                html += `<div class="brand-market-note">
                    No locally verified brand data found for ${userCountryName}.
                    Showing US FDA-registered brands below.
                </div>`;
            }

            const BRANDS_VISIBLE_LIMIT = 5;

            // ── Local market brands section ──
            if (localBrands.length) {
                const localSource = localBrands[0].source_authority || `FDA FAERS (${userCountry})`;
                html += `
                <div class="brand-tab-content" id="brand-tab-local" style="display:block;">
                    <p class="brands-subtitle">${localBrands.length} brand${localBrands.length > 1 ? 's' : ''} found in ${userCountryName}
                        <span class="brands-source-note">(Source: ${localSource})</span>
                    </p>
                    <div class="brands-list">`;
                localBrands.forEach((b, i) => {
                    const hidden = i >= BRANDS_VISIBLE_LIMIT ? ' brand-card-hidden' : '';
                    const overflow = i >= BRANDS_VISIBLE_LIMIT ? ' data-overflow="true"' : '';
                    html += _renderBrandCard(b, i, hidden, overflow);
                });
                html += `</div>`;
                if (localBrands.length > BRANDS_VISIBLE_LIMIT) {
                    const extra = localBrands.length - BRANDS_VISIBLE_LIMIT;
                    html += `<button class="show-more-brands-btn" data-target="brand-tab-local" data-extra="${extra}">
                        Show ${extra} more brand${extra > 1 ? 's' : ''} <span class="show-more-chevron">▾</span>
                    </button>`;
                }
                html += `</div>`;
            }

            // ── US FDA brands section ──
            if (usBrands.length) {
                const offset = localBrands.length;   // indices in flat array
                const tabVisible = isUS || !localBrands.length;
                html += `
                <div class="brand-tab-content" id="brand-tab-us" style="display:${tabVisible ? 'block' : 'none'};">
                    <p class="brands-subtitle">${usBrands.length} branded formulation${usBrands.length > 1 ? 's' : ''} from verified FDA label data.</p>
                    <div class="brands-list">`;
                usBrands.forEach((b, i) => {
                    const hidden = i >= BRANDS_VISIBLE_LIMIT ? ' brand-card-hidden' : '';
                    const overflow = i >= BRANDS_VISIBLE_LIMIT ? ' data-overflow="true"' : '';
                    html += _renderBrandCard(b, offset + i, hidden, overflow);
                });
                html += `</div>`;
                if (usBrands.length > BRANDS_VISIBLE_LIMIT) {
                    const extra = usBrands.length - BRANDS_VISIBLE_LIMIT;
                    html += `<button class="show-more-brands-btn" data-target="brand-tab-us" data-extra="${extra}">
                        Show ${extra} more brand${extra > 1 ? 's' : ''} <span class="show-more-chevron">▾</span>
                    </button>`;
                }
                html += `</div>`;
            }

            card.innerHTML = html;

            // ── Tab switching ──
            card.querySelectorAll('.brand-tab').forEach(tab => {
                tab.addEventListener('click', () => {
                    card.querySelectorAll('.brand-tab').forEach(t => t.classList.remove('active'));
                    tab.classList.add('active');
                    const which = tab.dataset.tab;
                    const localEl = document.getElementById('brand-tab-local');
                    const usEl = document.getElementById('brand-tab-us');
                    if (localEl) localEl.style.display = (which === 'local') ? 'block' : 'none';
                    if (usEl) usEl.style.display = (which === 'us') ? 'block' : 'none';
                });
            });

            // ── Expand/collapse ──
            card.querySelectorAll('.brand-expand-btn').forEach(btn => {
                btn.addEventListener('click', () => {
                    const idx = btn.dataset.idx;
                    const details = document.getElementById(`brand-details-${idx}`);
                    if (!details) return;
                    const isOpen = details.style.display !== 'none';
                    details.style.display = isOpen ? 'none' : 'block';
                    btn.textContent = isOpen ? 'Learn More ▾' : 'Collapse ▴';
                });
            });

            // ── Checkboxes ──
            card.querySelectorAll('.brand-check').forEach(cb => {
                cb.addEventListener('change', () => {
                    const checked = card.querySelectorAll('.brand-check:checked');
                    const btn = document.getElementById('compare-brands-btn');
                    if (btn) btn.disabled = checked.length < 2;
                });
            });

            // ── Show more / Show less ──
            card.querySelectorAll('.show-more-brands-btn').forEach(btn => {
                btn.addEventListener('click', () => {
                    const targetId = btn.dataset.target;
                    const container = document.getElementById(targetId);
                    if (!container) return;
                    const overflowCards = container.querySelectorAll('.brand-card[data-overflow]');
                    const isExpanded = btn.classList.contains('expanded');

                    overflowCards.forEach(c => {
                        if (isExpanded) {
                            c.classList.add('brand-card-hidden');
                        } else {
                            c.classList.remove('brand-card-hidden');
                        }
                    });

                    btn.classList.toggle('expanded');
                    if (isExpanded) {
                        const count = parseInt(btn.dataset.extra, 10) || overflowCards.length;
                        btn.innerHTML = `Show ${count} more brand${count > 1 ? 's' : ''} <span class="show-more-chevron">▾</span>`;
                    } else {
                        btn.innerHTML = `Show less <span class="show-more-chevron">▴</span>`;
                    }
                });
            });

            // ── Compare button ──
            const compareBtn = document.getElementById('compare-brands-btn');
            if (compareBtn) {
                compareBtn.addEventListener('click', () => {
                    const checkedIdxs = Array.from(card.querySelectorAll('.brand-check:checked'))
                        .map(cb => parseInt(cb.dataset.brandIdx, 10));
                    if (checkedIdxs.length >= 2) {
                        showBrandComparison(drug, checkedIdxs);
                    }
                });
            }

        } catch (err) {
            card.innerHTML = `
                <h3 class="druginfo-section-title">🏭 Brand Products</h3>
                <p style="color:var(--text-muted);font-size:13px;">Could not load brand data.</p>`;
        }
    }

    /**
     * Group brands that share the same base name (brand_name) but differ by
     * strength / dosage_form.  The "primary" entry keeps full details; extra
     * dosages are stored in `_variants` for compact chip rendering.
     */
    function _groupBrands(brands) {
        if (!brands || !brands.length) return brands;

        const groups = new Map(); // key → { primary, variants }
        for (const b of brands) {
            // Normalise key: lowercase brand_name, strip trailing whitespace
            const key = (b.brand_name || b.medicine_name || '').trim().toLowerCase();
            if (!key) { groups.set(Math.random().toString(), { primary: b, variants: [b] }); continue; }

            if (groups.has(key)) {
                groups.get(key).variants.push(b);
            } else {
                groups.set(key, { primary: { ...b }, variants: [b] });
            }
        }

        // For each group, pick the variant with the best pricing as primary
        const result = [];
        for (const { primary, variants } of groups.values()) {
            if (variants.length === 1) {
                primary._variants = variants;
                result.push(primary);
            } else {
                // Pick best primary (prefer one with NADAC pricing)
                const best = variants.slice().sort((a, c) => {
                    const aScore = (a.nadac_per_unit ? 2 : 0) + (a.strength ? 1 : 0);
                    const cScore = (c.nadac_per_unit ? 2 : 0) + (c.strength ? 1 : 0);
                    return cScore - aScore;
                })[0];
                const grouped = { ...best, _variants: variants };
                // Fill any blanks from other variants
                if (!grouped.product_type) {
                    grouped.product_type = variants.reduce((a, v) => a || v.product_type, '') || '';
                }
                if (!grouped.nadac_per_unit) {
                    const priced = variants.find(v => v.nadac_per_unit);
                    if (priced) {
                        grouped.nadac_per_unit = priced.nadac_per_unit;
                        grouped.nadac_unit = priced.nadac_unit;
                        grouped.nadac_effective_date = priced.nadac_effective_date;
                    }
                }
                if (!grouped.approximate_cost) {
                    grouped.approximate_cost = variants.reduce((a, v) => a || v.approximate_cost, '') || '';
                }
                result.push(grouped);
            }
        }
        return result;
    }

    /** Render a single brand card (used by both local and US sections). */
    function _renderBrandCard(b, idx, extraClass = '', extraAttr = '') {
        const combo = b.is_combination;
        const comboTag = combo
            ? '<span class="brand-tag combo">Combination</span>'
            : '<span class="brand-tag pure">Single Ingredient</span>';
        const productTag = b.product_type === 'HUMAN PRESCRIPTION DRUG'
            ? '<span class="brand-tag rx">Rx</span>'
            : (b.product_type === 'HUMAN OTC DRUG' ? '<span class="brand-tag otc">OTC</span>' : '');
        const countryTag = b.market_country && b.market_country !== 'US'
            ? `<span class="brand-tag market">${b.market_country}</span>` : '';

        // Variant chips (grouped dosages)
        const variants = b._variants || [];
        let variantHtml = '';
        if (variants.length > 1) {
            variantHtml = `<div class="brand-variants">
                ${variants.map(v => {
                    const label = v.strength || v.dosage_form || 'N/A';
                    let price = '';
                    if (v.nadac_per_unit) {
                        price = ` · ${_formatPrice(v.nadac_per_unit, 4)}/${v.nadac_unit || 'unit'}`;
                    } else if (v.approximate_cost) {
                        const pp = _parsePackPrice(v.approximate_cost);
                        if (pp) price = ` · ${pp.currency}${pp.price.toFixed(2)}`;
                    }
                    return `<span class="brand-variant-chip">${label}${price}</span>`;
                }).join('')}
            </div>`;
        }

        return `
        <div class="brand-card${extraClass}"${extraAttr} data-brand-idx="${idx}">
            <div class="brand-card-header">
                <label class="brand-check-label">
                    <input type="checkbox" class="brand-check" data-brand-id="${b.id}" data-brand-idx="${idx}">
                </label>
                <div class="brand-card-title">
                    <div class="brand-name-row">
                        <strong class="brand-name">${b.medicine_name || b.brand_name}</strong>
                        ${variants.length > 1 ? `<span class="brand-tag variant-count">${variants.length} dosages</span>` : ''}
                        ${comboTag}${productTag}${countryTag}
                    </div>
                    <div class="brand-manufacturer">by ${b.manufacturer || 'Unknown manufacturer'}</div>
                    ${variantHtml}
                </div>
                <button class="brand-expand-btn" data-idx="${idx}">Learn More ▾</button>
            </div>
            <div class="brand-details" id="brand-details-${idx}" style="display:none;">
                ${renderBrandDetails(b)}
            </div>
        </div>`;
    }

    function renderBrandDetails(b) {
        let html = '<div class="brand-details-inner">';

        // Composition
        html += '<div class="brand-detail-section">';
        html += '<h4 class="brand-detail-heading">🧪 Composition</h4>';
        const ingredients = b.active_ingredients || [];
        if (ingredients.length) {
            html += `<div class="brand-detail-row">
                <span class="detail-label">Active Ingredients:</span>
                <span class="detail-value">${ingredients.map(i => `<span class="ingredient-chip">${i}</span>`).join(' ')}</span>
            </div>`;
        }
        if (ingredients.length > 1) {
            html += `<div class="brand-detail-alert">⚠️ This is a <strong>combination product</strong> — contains additional active ingredients beyond the base drug.</div>`;
        } else {
            html += `<div class="brand-detail-ok">✅ <strong>Single-ingredient</strong> formulation — contains only the active drug.</div>`;
        }
        if (b.inactive_ingredients_summary) {
            html += `<div class="brand-detail-row">
                <span class="detail-label">Key Excipients:</span>
                <span class="detail-value detail-small">${formatText(b.inactive_ingredients_summary)}</span>
            </div>`;
        }
        html += '</div>';

        // Formulation
        html += '<div class="brand-detail-section">';
        html += '<h4 class="brand-detail-heading">💊 Formulation</h4>';
        if (b.dosage_form) html += `<div class="brand-detail-row"><span class="detail-label">Form:</span><span class="detail-value">${b.dosage_form}</span></div>`;
        if (b.strength) html += `<div class="brand-detail-row"><span class="detail-label">Strength:</span><span class="detail-value">${b.strength}</span></div>`;
        if (b.route) html += `<div class="brand-detail-row"><span class="detail-label">Route:</span><span class="detail-value">${b.route}</span></div>`;
        if (b.ndc) html += `<div class="brand-detail-row"><span class="detail-label">NDC:</span><span class="detail-value">${b.ndc}</span></div>`;
        // Product Type
        {
            const pt = b.product_type || '';
            let typeLabel = '';
            if (pt === 'HUMAN PRESCRIPTION DRUG') typeLabel = 'Rx (Prescription)';
            else if (pt === 'HUMAN OTC DRUG') typeLabel = 'OTC (Over-the-Counter)';
            else if (pt) typeLabel = pt.charAt(0).toUpperCase() + pt.slice(1).toLowerCase();
            if (typeLabel) html += `<div class="brand-detail-row"><span class="detail-label">Type:</span><span class="detail-value">${typeLabel}</span></div>`;
        }
        html += '</div>';

        // Pricing
        html += '<div class="brand-detail-section">';
        html += '<h4 class="brand-detail-heading">💰 Pricing</h4>';
        if (b.nadac_per_unit) {
            html += `<div class="brand-detail-row">
                <span class="detail-label">NADAC Unit Cost:</span>
                <span class="detail-value"><strong>${_formatPrice(b.nadac_per_unit, 4)}</strong>/${b.nadac_unit || 'unit'}</span>
            </div>`;
            html += `<div class="brand-detail-row">
                <span class="detail-label">Est. Monthly (30–90 day):</span>
                <span class="detail-value">${_formatPrice(b.nadac_per_unit * 30)} – ${_formatPrice(b.nadac_per_unit * 90)}</span>
            </div>`;
            if (b.nadac_effective_date) {
                html += `<div class="brand-detail-row"><span class="detail-label">Price Date:</span><span class="detail-value">${b.nadac_effective_date}</span></div>`;
            }
            html += `<div class="brand-source-note">Source: CMS NADAC (National Average Drug Acquisition Cost)</div>`;
        } else if (b.approximate_cost) {
            const pp = _parsePackPrice(b.approximate_cost);
            html += `<div class="brand-detail-row"><span class="detail-label">Pack Price:</span><span class="detail-value">${b.approximate_cost}</span></div>`;
            if (pp && pp.count > 1) {
                const unitP = pp.price / pp.count;
                html += `<div class="brand-detail-row"><span class="detail-label">Unit Price:</span><span class="detail-value">${pp.currency}${unitP.toFixed(2)}/unit</span></div>`;
                html += `<div class="brand-detail-row">
                    <span class="detail-label">Est. Monthly (30–90 day):</span>
                    <span class="detail-value">${pp.currency}${(unitP * 30).toFixed(2)} – ${pp.currency}${(unitP * 90).toFixed(2)} <small>(est.)</small></span>
                </div>`;
            }
        } else {
            html += `<div class="brand-detail-row"><span class="detail-value" style="color:var(--text-muted);">No verified pricing data for this formulation.</span></div>`;
        }
        html += '</div>';

        // Source
        if (b.source_url) {
            const srcLabel = (b.source_authority || 'FDA').includes('Verified')
                ? 'View Source ↗'
                : (b.source_authority || '').includes('Web')
                    ? 'View Source ↗'
                    : (b.source_authority || '').includes('Health Canada')
                        ? 'View Health Canada ↗'
                        : 'View FDA Label ↗';
            html += `<div class="brand-source-row">
                <span class="authority-badge" style="background:#1a5276;">${b.source_authority || 'FDA'}</span>
                <a href="${b.source_url}" target="_blank" rel="noopener">${srcLabel}</a>
            </div>`;
        } else if (b.source_authority) {
            html += `<div class="brand-source-row">
                <span class="authority-badge" style="background:#1a5276;">${b.source_authority}</span>
            </div>`;
        }

        html += '</div>';
        return html;
    }

    /* ── Brand Comparison Modal ── */

    function showBrandComparison(drug, brandIdxs) {
        // Remove any existing comparison modal
        const existing = document.getElementById('brand-comparison-modal');
        if (existing) existing.remove();

        // Pull brand data from the already-loaded cache (no extra API call)
        const brands = brandIdxs
            .map(idx => _brandsData[idx])
            .filter(Boolean);

        if (brands.length < 2) return;

        // Build comparison table
        const modalHtml = `
            <div id="brand-comparison-modal" class="brand-comparison-overlay">
                <div class="brand-comparison-content">
                    <div class="brand-comparison-header">
                        <h3>⚖️ Brand Comparison — ${drug.generic_name}</h3>
                        <button id="close-brand-comparison" class="btn btn-small btn-outline">✕ Close</button>
                    </div>
                    <div class="brand-comparison-scroll">
                        <table class="brand-comparison-table">
                            <thead>
                                <tr>
                                    <th>Attribute</th>
                                    ${brands.map(b => `<th>${b.medicine_name || b.brand_name}</th>`).join('')}
                                </tr>
                            </thead>
                            <tbody>
                                <tr>
                                    <td class="attr-label">Manufacturer</td>
                                    ${brands.map(b => `<td>${b.manufacturer || '<span class="unavailable">Information unavailable</span>'}</td>`).join('')}
                                </tr>
                                <tr>
                                    <td class="attr-label">Dosage Form</td>
                                    ${brands.map(b => `<td>${b.dosage_form || '<span class="unavailable">Information unavailable</span>'}</td>`).join('')}
                                </tr>
                                <tr>
                                    <td class="attr-label">Strength</td>
                                    ${brands.map(b => {
                                        const variants = b._variants || [];
                                        if (variants.length > 1) {
                                            return `<td>${variants.map(v => v.strength || '<span class="unavailable">N/A</span>').join('<br>')}</td>`;
                                        }
                                        return `<td>${b.strength || '<span class="unavailable">Information unavailable</span>'}</td>`;
                                    }).join('')}
                                </tr>
                                <tr>
                                    <td class="attr-label">Route</td>
                                    ${brands.map(b => `<td>${b.route || '<span class="unavailable">Information unavailable</span>'}</td>`).join('')}
                                </tr>
                                <tr>
                                    <td class="attr-label">Type</td>
                                    ${brands.map(b => {
                                        const pt = b.product_type || '';
                                        let t;
                                        if (pt === 'HUMAN PRESCRIPTION DRUG') t = 'Rx (Prescription)';
                                        else if (pt === 'HUMAN OTC DRUG') t = 'OTC (Over-the-Counter)';
                                        else if (pt.toLowerCase() === 'allopathy') t = 'Allopathy';
                                        else if (pt.toLowerCase() === 'ayurvedic') t = 'Ayurvedic';
                                        else if (pt.toLowerCase() === 'homeopathy') t = 'Homeopathy';
                                        else if (pt) t = pt;
                                        else t = '<span class="unavailable">Information unavailable</span>';
                                        return `<td>${t}</td>`;
                                    }).join('')}
                                </tr>
                                <tr class="highlight-row">
                                    <td class="attr-label">Composition</td>
                                    ${brands.map(b => {
                                        const c = b.is_combination;
                                        return `<td><span class="brand-tag ${c ? 'combo' : 'pure'}">${c ? 'Combination' : 'Single Ingredient'}</span></td>`;
                                    }).join('')}
                                </tr>
                                <tr>
                                    <td class="attr-label">Active Ingredients</td>
                                    ${brands.map(b => `<td class="detail-small">${(b.active_ingredients || []).join(', ') || '<span class="unavailable">Information unavailable</span>'}</td>`).join('')}
                                </tr>
                                <tr class="highlight-row">
                                    <td class="attr-label">NADAC Unit Price</td>
                                    ${brands.map(b => {
                                        if (b.nadac_per_unit) return `<td><strong>${_formatPrice(b.nadac_per_unit, 4)}</strong>/${b.nadac_unit || 'unit'}</td>`;
                                        return `<td class="unavailable">Information unavailable</td>`;
                                    }).join('')}
                                </tr>
                                <tr>
                                    <td class="attr-label">Pack Price</td>
                                    ${brands.map(b => {
                                        const pp = _parsePackPrice(b.approximate_cost);
                                        if (pp) return `<td>${pp.currency}${pp.price.toFixed(2)} ${pp.count > 1 ? `(${pp.count} units)` : ''}</td>`;
                                        return `<td class="unavailable">Information unavailable</td>`;
                                    }).join('')}
                                </tr>
                                <tr class="highlight-row">
                                    <td class="attr-label">Est. Monthly Cost</td>
                                    ${brands.map(b => {
                                        // Prefer NADAC-based range (30-90 days)
                                        if (b.nadac_per_unit) return `<td>${_formatPrice(b.nadac_per_unit * 30)} – ${_formatPrice(b.nadac_per_unit * 90)}</td>`;
                                        // Try to compute from pack price (assume 1 unit/day for tablets/capsules)
                                        const pp = _parsePackPrice(b.approximate_cost);
                                        if (pp && pp.count > 0) {
                                            const unitP = pp.price / pp.count;
                                            const lo = unitP * 30, hi = unitP * 90;
                                            return `<td>${pp.currency}${lo.toFixed(2)} – ${pp.currency}${hi.toFixed(2)} <small>(est.)</small></td>`;
                                        }
                                        // Check variants
                                        const pricedV = (b._variants || []).find(v => v.nadac_per_unit);
                                        if (pricedV) return `<td>${_formatPrice(pricedV.nadac_per_unit * 30)} – ${_formatPrice(pricedV.nadac_per_unit * 90)}</td>`;
                                        return `<td class="unavailable">Information unavailable</td>`;
                                    }).join('')}
                                </tr>
                                <tr>
                                    <td class="attr-label">NDC</td>
                                    ${brands.map(b => {
                                        if (b.ndc) return `<td class="detail-small">${b.ndc}</td>`;
                                        if (b.market_country && b.market_country !== 'US') return `<td class="detail-small" style="color:var(--text-muted);">N/A (${b.market_country})</td>`;
                                        return `<td class="unavailable">Information unavailable</td>`;
                                    }).join('')}
                                </tr>
                                <tr>
                                    <td class="attr-label">Source</td>
                                    ${brands.map(b => `<td>${b.source_url ? `<a href="${b.source_url}" target="_blank" rel="noopener">${b.source_authority || 'FDA'} ↗</a>` : (b.source_authority || '<span class="unavailable">Information unavailable</span>')}</td>`).join('')}
                                </tr>
                                <tr>
                                    <td class="attr-label">Market</td>
                                    ${brands.map(b => `<td>${b.market_country || 'US'}</td>`).join('')}
                                </tr>
                            </tbody>
                        </table>
                    </div>
                </div>
            </div>`;

        // Inject modal into body
        document.body.insertAdjacentHTML('beforeend', modalHtml);

        // Close button
        document.getElementById('close-brand-comparison').addEventListener('click', () => {
            document.getElementById('brand-comparison-modal').remove();
        });

        // Close on backdrop click (outside the white content box)
        document.getElementById('brand-comparison-modal').addEventListener('click', (e) => {
            if (e.target.id === 'brand-comparison-modal') {
                e.target.remove();
            }
        });

        // Close on Escape key
        const escHandler = (e) => {
            if (e.key === 'Escape') {
                const modal = document.getElementById('brand-comparison-modal');
                if (modal) modal.remove();
                document.removeEventListener('keydown', escHandler);
            }
        };
        document.addEventListener('keydown', escHandler);
    }

    return { render };
})();
