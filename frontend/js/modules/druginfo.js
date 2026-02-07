/**
 * Clerasense – Drug Information Module
 * Displays comprehensive drug profiles with pricing, safety,
 * dosage, and interaction data from verified regulatory sources.
 * This is a LOOKUP page, not a chat interface.
 */

const DrugInfoModule = (() => {

    /* ── Currency state ── */
    let _currency = 'USD';
    let _rates = null;          // exchange rates vs USD
    let _locationNote = '';     // e.g. "Based on your approximate location (India)"

    const CURRENCY_SYMBOLS = {
        USD: '$', EUR: '€', GBP: '£', INR: '₹', JPY: '¥', CNY: '¥',
        AUD: 'A$', CAD: 'C$', CHF: 'CHF', KRW: '₩', BRL: 'R$',
        MXN: 'MX$', ZAR: 'R', SGD: 'S$', HKD: 'HK$', SEK: 'kr',
        NOK: 'kr', DKK: 'kr', NZD: 'NZ$', THB: '฿', MYR: 'RM',
        PHP: '₱', IDR: 'Rp', AED: 'AED', SAR: 'SAR', BDT: '৳',
        PKR: 'Rs', LKR: 'Rs', NPR: 'Rs', EGP: 'E£', NGN: '₦',
    };

    const COUNTRY_TO_CURRENCY = {
        US: 'USD', GB: 'GBP', IN: 'INR', JP: 'JPY', CN: 'CNY',
        AU: 'AUD', CA: 'CAD', CH: 'CHF', KR: 'KRW', BR: 'BRL',
        MX: 'MXN', ZA: 'ZAR', SG: 'SGD', HK: 'HKD', SE: 'SEK',
        NO: 'NOK', DK: 'DKK', NZ: 'NZD', TH: 'THB', MY: 'MYR',
        PH: 'PHP', ID: 'IDR', AE: 'AED', SA: 'SAR', BD: 'BDT',
        PK: 'PKR', LK: 'LKR', NP: 'NPR', EG: 'EGP', NG: 'NGN',
        DE: 'EUR', FR: 'EUR', IT: 'EUR', ES: 'EUR', NL: 'EUR',
        BE: 'EUR', AT: 'EUR', PT: 'EUR', IE: 'EUR', FI: 'EUR',
        GR: 'EUR', LU: 'EUR',
    };

    /** Detect approximate location via IP (no GPS / no precise location). */
    async function _detectCurrency() {
        try {
            const res = await fetch('https://ipapi.co/json/', { signal: AbortSignal.timeout(4000) });
            if (!res.ok) return;
            const geo = await res.json();
            const cc = (geo.country_code || '').toUpperCase();
            const country = geo.country_name || cc;
            const mapped = COUNTRY_TO_CURRENCY[cc];
            if (mapped && mapped !== 'USD') {
                _currency = mapped;
                _locationNote = `Showing prices in ${mapped} based on your approximate location (${country}). No precise location is accessed.`;
            }
        } catch { /* fallback to USD silently */ }
    }

    /** Fetch exchange rates (USD base). Cached for session. */
    async function _loadRates() {
        if (_rates) return;
        try {
            const res = await fetch('https://open.er-api.com/v6/latest/USD', { signal: AbortSignal.timeout(5000) });
            if (!res.ok) return;
            const data = await res.json();
            if (data.rates) _rates = data.rates;
        } catch { /* will stay null → show USD */ }
    }

    function _convertPrice(usd) {
        if (!usd || !_rates || _currency === 'USD') return usd;
        const rate = _rates[_currency];
        if (!rate) return usd;
        return usd * rate;
    }

    function _formatPrice(usd, decimals = 2) {
        const sym = CURRENCY_SYMBOLS[_currency] || _currency + ' ';
        const converted = _convertPrice(usd);
        if (converted === null || converted === undefined) return 'N/A';
        return `${sym}${converted.toFixed(decimals)}`;
    }

    /* ── Lifecycle hooks ── */
    // Kick off currency detection + rate loading once on first import
    (async () => {
        await _detectCurrency();
        await _loadRates();
    })();

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
                    <div class="form-group" style="flex:1;margin-bottom:0;">
                        <label>Drug Name</label>
                        <input type="text" id="druginfo-input"
                               placeholder="e.g., Metformin, Atorvastatin, Lisinopril"
                               autocomplete="off">
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

        btn.addEventListener('click', lookupDrug);
        input.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') lookupDrug();
        });
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
        await _loadRates();

        // Fetch drug profile AND pricing in parallel
        const [rawDrug, pricingData] = await Promise.all([
            API.getDrugByName(name),
            API.getPricing(name),
        ]);

        if (rawDrug.error) {
            resultsEl.innerHTML = `<p class="error-msg">${rawDrug.error}</p>`;
            return;
        }

        // Unwrap the { drug: { ... } } envelope
        const drug = rawDrug.drug || rawDrug;

        renderDrugProfile(drug, pricingData, resultsEl);
        updateContextPanel(drug);
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
                       <strong>Mechanism of Action:</strong> ${truncate(drug.mechanism_of_action, 600)}
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
                    ${formatText(ind.approved_use, 500)}
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
                        <div class="dosage-value">${formatText(d.adult_dosage, 500)}</div>
                    </div>`;
                }
                if (d.pediatric_dosage) {
                    html += `<div class="druginfo-dosage-cell">
                        <div class="dosage-label">Pediatric Dosage</div>
                        <div class="dosage-value">${formatText(d.pediatric_dosage, 500)}</div>
                    </div>`;
                }
                if (d.renal_adjustment) {
                    html += `<div class="druginfo-dosage-cell">
                        <div class="dosage-label">Renal Adjustment</div>
                        <div class="dosage-value">${formatText(d.renal_adjustment, 500)}</div>
                    </div>`;
                }
                if (d.hepatic_adjustment) {
                    html += `<div class="druginfo-dosage-cell">
                        <div class="dosage-label">Hepatic Adjustment</div>
                        <div class="dosage-value">${formatText(d.hepatic_adjustment, 500)}</div>
                    </div>`;
                }
                html += `</div>`;
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
                        ${formatText(w.black_box_warnings, 800)}
                    </div>`;
                }
                if (w.contraindications) {
                    html += `<div class="druginfo-item">
                        <strong>🚫 Contraindications:</strong>
                        ${formatText(w.contraindications, 800)}
                    </div>`;
                }
                if (w.pregnancy_risk) {
                    html += `<div class="druginfo-item">
                        <strong>🤰 Pregnancy:</strong>
                        ${formatText(w.pregnancy_risk, 500)}
                    </div>`;
                }
                if (w.lactation_risk) {
                    html += `<div class="druginfo-item">
                        <strong>🍼 Lactation:</strong>
                        ${formatText(w.lactation_risk, 500)}
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
                    <span class="interaction-drug">${ix.interacting_drug}</span>
                    <span class="interaction-severity" style="background:${sevColor};">${ix.severity}</span>
                    <span class="interaction-desc">${ix.description}</span>
                </div>`;
            });
            html += `</div></div>`;
        }

        // ── Pricing & Reimbursement ──
        html += renderPricingSection(pricing);

        container.innerHTML = html;

        // Bind currency selector change handler
        const sel = document.getElementById('currency-select');
        if (sel) {
            sel.addEventListener('change', () => {
                _currency = sel.value;
                // Re-render pricing section only
                const pricingCard = document.getElementById('pricing-section-card');
                if (pricingCard) {
                    pricingCard.outerHTML = renderPricingSection(pricing);
                    // Re-bind
                    const newSel = document.getElementById('currency-select');
                    if (newSel) {
                        newSel.addEventListener('change', () => {
                            _currency = newSel.value;
                            const pc = document.getElementById('pricing-section-card');
                            if (pc) {
                                pc.outerHTML = renderPricingSection(pricing);
                                bindCurrencySelector(pricing);
                            }
                        });
                    }
                }
            });
        }
    }

    function bindCurrencySelector(pricing) {
        const sel = document.getElementById('currency-select');
        if (!sel) return;
        sel.addEventListener('change', () => {
            _currency = sel.value;
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
        const currencyOptions = Object.keys(CURRENCY_SYMBOLS).map(c =>
            `<option value="${c}" ${c === _currency ? 'selected' : ''}>${c} (${CURRENCY_SYMBOLS[c]})</option>`
        ).join('');

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
        if (_locationNote && _currency !== 'USD') {
            html += `<div class="currency-location-note">${_locationNote}</div>`;
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
                        ${_currency !== 'USD' ? `<span class="pricing-orig">(US$${p.nadac_per_unit.toFixed(4)})</span>` : ''}
                        ${p.nadac_effective_date ? `<span class="pricing-date">as of ${p.nadac_effective_date}</span>` : ''}
                    </div>`;
                }

                html += renderSourceBadge(p.source, isNadac ? 'NADAC' : null);
                html += `</div>`;
            });
        } else {
            html += '<p style="color:var(--text-muted);font-size:13px;">No verified pricing data available.</p>';
        }

        // Reimbursement
        if (data.reimbursement && data.reimbursement.length) {
            html += '<h4 class="druginfo-subsection-title">Government Reimbursement</h4>';
            data.reimbursement.forEach(r => {
                html += `<div class="reimbursement-item">
                    <div class="reimbursement-scheme">${r.scheme_name}</div>
                    <div>${r.coverage_notes || 'No additional notes.'}</div>
                    ${renderSourceBadge(r.source)}
                </div>`;
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
        return str.length > max ? str.substring(0, max) + '…' : str;
    }

    /**
     * Format a long medical text blob into readable bullet-pointed HTML.
     * Splits on sentence boundaries; deduplicates; wraps in <ul>.
     */
    function formatText(raw, maxLen) {
        if (!raw) return '';
        let text = raw.trim();
        if (maxLen) text = truncate(text, maxLen);

        // Split into sentences at: period+space, semicolons, or existing bullet chars
        let parts = text
            .split(/(?<=[.;])\s+|\s*[•●▪]\s*/)
            .map(s => s.trim())
            .filter(s => s.length > 8);  // drop tiny fragments

        // Deduplicate (some data has repeated sentences)
        const seen = new Set();
        parts = parts.filter(p => {
            const key = p.toLowerCase().replace(/[^a-z0-9]/g, '').slice(0, 60);
            if (seen.has(key)) return false;
            seen.add(key);
            return true;
        });

        // If 1 short item, just return as paragraph
        if (parts.length <= 1 && text.length < 150) {
            return `<p>${text}</p>`;
        }

        if (parts.length <= 1) {
            // Still one block but long — return as paragraph
            return `<p>${text}</p>`;
        }

        return '<ul class="druginfo-bullets">' +
            parts.map(p => `<li>${p.replace(/^\(\s*\d+\s*\)\s*/, '').replace(/^\d+\.\d+\s*/, '')}</li>`).join('') +
            '</ul>';
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

    return { render };
})();
