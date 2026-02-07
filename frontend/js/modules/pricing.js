/**
 * Clerasense – Pricing & Reimbursement Module
 * Displays estimated costs, generic availability, and government scheme coverage.
 */

const PricingModule = (() => {

    function render(container) {
        container.innerHTML = `
            <div class="pricing-container">
                <div class="chat-header">
                    <h2>Pricing & Reimbursement</h2>
                    <p>View approximate cost estimates, generic availability, and government coverage schemes.</p>
                </div>
                <div class="disclaimer-banner">
                    Prices are approximate estimates from publicly available sources.
                    Actual costs may vary by pharmacy, region, insurance plan, and time of purchase.
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
        resultsEl.innerHTML = '<div class="loading">Looking up pricing…</div>';

        const data = await API.getPricing(name);

        if (data.error) {
            resultsEl.innerHTML = `<p class="error-msg">${data.error}</p>`;
            return;
        }

        renderPricing(data, resultsEl);
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
                html += `
                    <div class="pricing-detail">
                        <span class="pricing-label">Approximate Cost</span>
                        <span class="pricing-value">${p.approximate_cost || 'N/A'}</span>
                    </div>
                    <div class="pricing-detail">
                        <span class="pricing-label">Generic Available</span>
                        <span class="pricing-value">${p.generic_available ? 'Yes' : 'No'}</span>
                    </div>
                `;
                if (p.source) {
                    html += `<div style="font-size:11px;color:var(--text-muted);margin-top:4px;">
                        📄 ${p.source.authority} — ${p.source.document_title}
                    </div>`;
                }
            });
        } else {
            html += '<p style="color:var(--text-muted);font-size:13px;">Pricing data not available in verified sources.</p>';
        }

        // Reimbursement
        if (data.reimbursement && data.reimbursement.length) {
            html += '<h3 class="section-heading" style="margin-top:16px;">Government Reimbursement Coverage</h3>';
            data.reimbursement.forEach(r => {
                html += `
                    <div class="reimbursement-item">
                        <div class="reimbursement-scheme">${r.scheme_name}</div>
                        <div>${r.coverage_notes || 'No additional notes.'}</div>
                        ${r.source ? `<div style="font-size:11px;color:var(--text-muted);margin-top:4px;">
                            📄 ${r.source.authority} — ${r.source.document_title}
                        </div>` : ''}
                    </div>
                `;
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
