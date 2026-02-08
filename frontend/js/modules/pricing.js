/**
 * Clerasense – Pricing & Reimbursement Module
 * Shows NADAC real government pricing, generic availability,
 * and government scheme coverage with clear source attribution.
 */

const PricingModule = (() => {

    function render(container) {
        container.innerHTML = `
            <div class="pricing-container">
                <div class="chat-header">
                    <h2>Pricing & Reimbursement</h2>
                    <p>View real drug pricing from CMS NADAC, generic availability, and government coverage.</p>
                </div>
                <div class="disclaimer-banner">
                    Pricing data sourced from the CMS National Average Drug Acquisition Cost (NADAC) database,
                    updated weekly. Actual retail costs may vary by pharmacy, region, and insurance plan.
                </div>
                <div style="display:flex;gap:10px;margin-bottom:20px;">
                    <div class="form-group" style="flex:1;margin-bottom:0;">
                        <label>Drug Name</label>
                        <input type="text" id="pricing-drug" placeholder="e.g., Metformin">
                    </div>
                    <button id="pricing-lookup-btn" class="btn btn-primary"
                            style="width:auto;align-self:flex-end;height:42px;">
                        Look Up
                    </button>
                </div>
                <div id="pricing-results"></div>
            </div>
        `;

        const input = document.getElementById('pricing-drug');
        const btn = document.getElementById('pricing-lookup-btn');

        btn.addEventListener('click', lookupPricing);
        input.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') lookupPricing();
        });
    }

    async function lookupPricing() {
        const name = document.getElementById('pricing-drug').value.trim();
        if (!name) {
            document.getElementById('pricing-results').innerHTML =
                '<p class="error-msg">Please enter a drug name.</p>';
            return;
        }

        const resultsEl = document.getElementById('pricing-results');
        resultsEl.innerHTML = '<div class="loading">Looking up real pricing data from CMS NADAC & FDA… may take a moment for new drugs.</div>';

        const data = await API.getPricing(name, App.getUserCountry() || 'US');

        if (data.error) {
            resultsEl.innerHTML = `<p class="error-msg">${data.error}</p>`;
            return;
        }

        renderPricing(data, resultsEl);
    }

    function renderSourceBadge(source, extraLabel) {
        if (!source) return '';
        const authority = source.authority || 'Unknown';
        const badgeColors = {
            'FDA': '#1a5276',
            'NIH/NLM': '#196f3d',
            'CMS': '#7d3c98',
        };
        const color = badgeColors[authority] || '#555';
        const title = source.document_title || '';
        const year = source.publication_year || '';
        const url = source.url || '';
        const effDate = source.effective_date ? ` | Effective: ${source.effective_date}` : '';
        const retrieved = source.data_retrieved_at
            ? ` | Retrieved: ${new Date(source.data_retrieved_at).toLocaleDateString()}`
            : '';

        return `<div style="margin-top:8px;padding:6px 10px;background:#f8f9fa;border-left:3px solid ${color};border-radius:4px;font-size:11px;line-height:1.4;">
            <span style="display:inline-block;padding:1px 6px;background:${color};color:#fff;border-radius:3px;font-size:10px;font-weight:600;margin-right:6px;">${authority}</span>
            ${extraLabel ? `<span style="display:inline-block;padding:1px 6px;background:#e8f5e9;color:#2e7d32;border-radius:3px;font-size:10px;font-weight:600;margin-right:6px;">${extraLabel}</span>` : ''}
            <span>${title} (${year}${effDate}${retrieved})</span>
            ${url ? ` <a href="${url}" target="_blank" rel="noopener" style="color:${color};margin-left:6px;">Verify Source ↗</a>` : ''}
        </div>`;
    }

    function renderPricing(data, container) {
        let html = `
            <div class="pricing-card">
                <div class="pricing-header">
                    <div>
                        <div class="pricing-drug-name">${data.drug}</div>
                        ${data.brand_names && data.brand_names.length
                            ? `<div style="font-size:12px;color:var(--text-muted);">
                                   Brand: ${data.brand_names.join(', ')}
                               </div>`
                            : ''}
                    </div>
                    ${data.generic_available
                        ? '<span class="generic-badge">Generic Available</span>'
                        : '<span class="generic-badge" style="background:#fef2f2;color:var(--danger);">Brand Only</span>'}
                </div>
        `;

        // Pricing details
        if (data.pricing && data.pricing.length) {
            data.pricing.forEach(p => {
                const isNadac = p.pricing_source === 'NADAC';
                const sourceLabel = isNadac ? 'NADAC Real Price' : 'Estimate';
                const priceBg = isNadac ? '#e8f8f5' : '#fef9e7';
                const priceColor = isNadac ? '#1e8449' : '#b7950b';

                html += `<div style="background:${priceBg};border-radius:6px;padding:12px;margin:8px 0;">`;

                // Header with source type badge
                html += `<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;">
                    <span style="font-weight:600;color:${priceColor};">${sourceLabel}</span>
                    ${isNadac ? '<span style="font-size:10px;padding:2px 6px;background:#d5f5e3;color:#1e8449;border-radius:3px;">Government Data</span>' : '<span style="font-size:10px;padding:2px 6px;background:#fdebd0;color:#b7950b;border-radius:3px;">Approximate</span>'}
                </div>`;

                html += `<div class="pricing-detail">
                    <span class="pricing-label">Cost</span>
                    <span class="pricing-value" style="color:${priceColor};font-weight:700;">${p.approximate_cost || 'N/A'}</span>
                </div>`;

                // Show NADAC-specific details
                if (isNadac && p.nadac_per_unit) {
                    html += `<div class="pricing-detail">
                        <span class="pricing-label">NADAC Unit Price</span>
                        <span class="pricing-value">$${p.nadac_per_unit.toFixed(4)}/unit</span>
                    </div>`;
                }
                if (p.nadac_ndc) {
                    html += `<div class="pricing-detail">
                        <span class="pricing-label">NDC</span>
                        <span class="pricing-value">${p.nadac_ndc}</span>
                    </div>`;
                }
                if (p.nadac_package_description) {
                    html += `<div class="pricing-detail">
                        <span class="pricing-label">Package</span>
                        <span class="pricing-value">${p.nadac_package_description}</span>
                    </div>`;
                }
                if (p.nadac_effective_date) {
                    html += `<div class="pricing-detail">
                        <span class="pricing-label">Pricing Date</span>
                        <span class="pricing-value">${p.nadac_effective_date}</span>
                    </div>`;
                }

                html += `<div class="pricing-detail">
                    <span class="pricing-label">Generic Available</span>
                    <span class="pricing-value">${p.generic_available ? '✅ Yes' : '❌ No'}</span>
                </div>`;

                // Source badge
                html += renderSourceBadge(p.source, isNadac ? 'NADAC' : null);
                html += `</div>`;
            });
        } else {
            html += '<p style="color:var(--text-muted);font-size:13px;">Pricing data not available in verified sources.</p>';
        }

        // Reimbursement – country-specific government schemes
        if (data.reimbursement && data.reimbursement.length) {
            const countryLabel = data.reimbursement_country || 'your country';
            html += `<h3 class="section-heading" style="margin-top:16px;">🏛️ Government Reimbursement Schemes</h3>`;
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

        html += '</div>';

        if (data.disclaimer) {
            html += `<div class="disclaimer-banner">${data.disclaimer}</div>`;
        }

        container.innerHTML = html;
    }

    return { render };
})();
