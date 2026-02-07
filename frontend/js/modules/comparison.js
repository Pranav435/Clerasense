/**
 * Clerasense – Drug Comparison Module
 * Side-by-side factual comparison of 2–4 drugs.
 * No ranking. No recommendations.
 */

const ComparisonModule = (() => {

    function render(container) {
        container.innerHTML = `
            <div class="comparison-container">
                <div class="chat-header">
                    <h2>Drug Comparison</h2>
                    <p>Compare 2–4 drugs on factual parameters. No ranking or recommendation is provided.</p>
                </div>
                <div class="disclaimer-banner">
                    Comparison displays factual, source-backed data only. No drug is ranked as "better" or "preferred."
                    Clinical decision-making must consider patient-specific factors.
                </div>
                <div class="comparison-input">
                    <div class="form-group">
                        <label>Drug 1</label>
                        <input type="text" id="cmp-drug-1" placeholder="e.g., Metformin">
                    </div>
                    <div class="form-group">
                        <label>Drug 2</label>
                        <input type="text" id="cmp-drug-2" placeholder="e.g., Lisinopril">
                    </div>
                    <div class="form-group">
                        <label>Drug 3 (optional)</label>
                        <input type="text" id="cmp-drug-3" placeholder="e.g., Atorvastatin">
                    </div>
                    <div class="form-group">
                        <label>Drug 4 (optional)</label>
                        <input type="text" id="cmp-drug-4" placeholder="">
                    </div>
                    <button id="cmp-compare-btn" class="btn btn-primary" style="width:auto;height:42px;align-self:flex-end;">
                        Compare
                    </button>
                </div>
                <div id="cmp-results"></div>
            </div>
        `;

        document.getElementById('cmp-compare-btn').addEventListener('click', runComparison);
    }

    async function runComparison() {
        const names = [];
        for (let i = 1; i <= 4; i++) {
            const val = document.getElementById(`cmp-drug-${i}`).value.trim();
            if (val) names.push(val);
        }

        if (names.length < 2) {
            document.getElementById('cmp-results').innerHTML =
                '<p class="error-msg">Please enter at least 2 drug names.</p>';
            return;
        }

        const resultsEl = document.getElementById('cmp-results');
        resultsEl.innerHTML = '<div class="loading">Loading comparison…</div>';

        const data = await API.compareDrugs(names);

        if (data.error) {
            resultsEl.innerHTML = `<p class="error-msg">${data.error}</p>`;
            return;
        }

        renderComparisonTable(data, resultsEl);
    }

    function renderComparisonTable(data, container) {
        const drugs = data.comparison || [];
        if (drugs.length === 0) {
            container.innerHTML = '<p>No drugs found for comparison.</p>';
            return;
        }

        const dimensions = [
            { key: 'drug_class', label: 'Drug Class' },
            { key: 'mechanism_of_action', label: 'Mechanism of Action' },
            { key: 'indications', label: 'Approved Indications', format: 'indications' },
            { key: 'dosage_guidelines', label: 'Adult Dosage', format: 'dosage' },
            { key: 'safety_warnings', label: 'Key Safety Warnings', format: 'safety' },
            { key: 'interactions', label: 'Notable Interactions', format: 'interactions' },
            { key: 'pricing', label: 'Approximate Cost', format: 'pricing' },
        ];

        let html = '<table class="comparison-table"><thead><tr>';
        html += '<th>Parameter</th>';
        drugs.forEach(d => {
            html += `<th>${d.generic_name}<br><small>${(d.brand_names || []).join(', ')}</small></th>`;
        });
        html += '</tr></thead><tbody>';

        dimensions.forEach(dim => {
            html += '<tr>';
            html += `<td class="dimension-label">${dim.label}</td>`;
            drugs.forEach(drug => {
                html += `<td>${formatCell(drug, dim)}</td>`;
            });
            html += '</tr>';
        });

        html += '</tbody></table>';

        if (data.not_found && data.not_found.length) {
            html += `<p style="margin-top:12px;color:var(--warning);font-size:13px;">
                Not found in database: ${data.not_found.join(', ')}</p>`;
        }

        if (data.disclaimer) {
            html += `<div class="disclaimer-banner" style="margin-top:16px;">${data.disclaimer}</div>`;
        }

        container.innerHTML = html;
    }

    function formatCell(drug, dim) {
        switch (dim.format) {
            case 'indications':
                return (drug.indications || [])
                    .map(i => `• ${truncate(i.approved_use, 120)}`)
                    .join('<br>') || 'N/A';
            case 'dosage':
                return (drug.dosage_guidelines || [])
                    .map(d => d.adult_dosage || 'N/A')
                    .join('<br>') || 'N/A';
            case 'safety':
                return (drug.safety_warnings || [])
                    .map(s => {
                        const parts = [];
                        if (s.black_box_warnings) parts.push(`⚠️ ${truncate(s.black_box_warnings, 100)}`);
                        if (s.pregnancy_risk) parts.push(`Pregnancy: ${s.pregnancy_risk}`);
                        return parts.join('<br>');
                    }).join('<br>') || 'N/A';
            case 'interactions':
                return (drug.interactions || []).slice(0, 3)
                    .map(x => `${x.interacting_drug} <span class="drug-tag">${x.severity}</span>`)
                    .join('<br>') || 'None documented';
            case 'pricing':
                return (drug.pricing || [])
                    .map(p => p.approximate_cost || 'N/A')
                    .join('<br>') || 'N/A';
            default:
                return drug[dim.key] || 'N/A';
        }
    }

    function truncate(str, max) {
        if (!str) return '';
        return str.length > max ? str.substring(0, max) + '…' : str;
    }

    return { render };
})();
