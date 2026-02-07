/**
 * Clerasense – Safety Checker Module
 * Checks contraindications, drug interactions, and safety warnings.
 * Information tool only — NOT a prescription review or approval system.
 */

const SafetyModule = (() => {

    function render(container) {
        container.innerHTML = `
            <div class="safety-container">
                <div class="chat-header">
                    <h2>Prescription Safety Checker</h2>
                    <p>Check for contraindications, interactions, and safety warnings across multiple drugs.</p>
                </div>
                <div class="disclaimer-banner">
                    ⚠️ DISCLAIMER: This tool provides informational alerts from verified regulatory sources.
                    It is NOT a substitute for clinical judgment. The prescribing physician is solely
                    responsible for all prescribing decisions.
                </div>
                <div class="safety-input">
                    <div class="form-group">
                        <label>Drug Names (comma-separated)</label>
                        <input type="text" id="safety-drugs"
                               placeholder="e.g., Metformin, Lisinopril, Atorvastatin">
                    </div>
                    <div class="form-group">
                        <label>Context Flags (optional)</label>
                        <div class="context-flags">
                            <label class="context-flag">
                                <input type="checkbox" id="ctx-pregnancy"> Pregnancy
                            </label>
                            <label class="context-flag">
                                <input type="checkbox" id="ctx-renal"> Renal Impairment
                            </label>
                            <label class="context-flag">
                                <input type="checkbox" id="ctx-hepatic"> Hepatic Impairment
                            </label>
                        </div>
                    </div>
                    <button id="safety-check-btn" class="btn btn-primary" style="width:auto;margin-top:8px;">
                        Run Safety Check
                    </button>
                </div>
                <div id="safety-results"></div>
            </div>
        `;

        document.getElementById('safety-check-btn').addEventListener('click', runSafetyCheck);
    }

    async function runSafetyCheck() {
        const drugsInput = document.getElementById('safety-drugs').value.trim();
        if (!drugsInput) {
            document.getElementById('safety-results').innerHTML =
                '<p class="error-msg">Please enter at least one drug name.</p>';
            return;
        }

        const drugNames = drugsInput.split(',').map(s => s.trim()).filter(Boolean);
        const context = {
            pregnancy: document.getElementById('ctx-pregnancy').checked,
            renal_impairment: document.getElementById('ctx-renal').checked,
            hepatic_impairment: document.getElementById('ctx-hepatic').checked,
        };

        const resultsEl = document.getElementById('safety-results');
        resultsEl.innerHTML = '<div class="loading">Running safety checks…</div>';

        const data = await API.checkSafety(drugNames, context);

        if (data.error) {
            resultsEl.innerHTML = `<p class="error-msg">${data.error}</p>`;
            return;
        }

        renderSafetyResults(data, resultsEl);
    }

    function renderSafetyResults(data, container) {
        let html = '';

        // Not found drugs
        if (data.drugs_not_found && data.drugs_not_found.length) {
            html += `<div class="alert-card severity-moderate">
                <div class="alert-title">⚠️ Drugs Not Found</div>
                <p>The following drugs were not found in the verified database:
                   <strong>${data.drugs_not_found.join(', ')}</strong>.
                   Safety information could not be checked for these drugs.</p>
            </div>`;
        }

        // Interaction alerts (highest priority)
        if (data.interaction_alerts && data.interaction_alerts.length) {
            html += '<h3 class="section-heading">Drug-Drug Interactions</h3>';
            data.interaction_alerts.forEach(alert => {
                html += `
                    <div class="alert-card severity-${alert.severity}">
                        <div class="alert-title">
                            ${severityIcon(alert.severity)} ${alert.drug_a} + ${alert.drug_b}
                            <span class="drug-tag">${alert.severity.toUpperCase()}</span>
                        </div>
                        <p>${alert.description}</p>
                        ${renderSource(alert.source)}
                    </div>
                `;
            });
        }

        // Context alerts
        if (data.context_alerts && data.context_alerts.length) {
            html += '<h3 class="section-heading">Context-Specific Alerts</h3>';
            data.context_alerts.forEach(alert => {
                html += `
                    <div class="alert-card severity-major">
                        <div class="alert-title">
                            🚨 ${alert.drug} — ${formatAlertType(alert.alert_type)}
                        </div>
                        <p>${alert.detail || alert.risk_category || ''}</p>
                        ${renderSource(alert.source)}
                    </div>
                `;
            });
        }

        // Safety warnings
        if (data.safety_warnings && data.safety_warnings.length) {
            html += '<h3 class="section-heading">Safety Warnings</h3>';
            data.safety_warnings.forEach(w => {
                html += `
                    <div class="alert-card severity-moderate">
                        <div class="alert-title">${w.drug}</div>
                        ${w.contraindications ? `<p><strong>Contraindications:</strong> ${w.contraindications}</p>` : ''}
                        ${w.black_box_warnings ? `<p><strong>Black Box Warning:</strong> ${w.black_box_warnings}</p>` : ''}
                        ${w.pregnancy_risk ? `<p><strong>Pregnancy:</strong> ${w.pregnancy_risk}</p>` : ''}
                        ${w.lactation_risk ? `<p><strong>Lactation:</strong> ${w.lactation_risk}</p>` : ''}
                        ${renderSource(w.source)}
                    </div>
                `;
            });
        }

        if (!html) {
            html = '<div class="empty-state"><h3>No alerts found</h3><p>No safety concerns were identified for the provided drugs and context.</p></div>';
        }

        // Disclaimer at bottom
        if (data.disclaimer) {
            html += `<div class="disclaimer-banner" style="margin-top:20px;">${data.disclaimer}</div>`;
        }

        container.innerHTML = html;

        // Update warnings panel
        updateWarningsPanel(data);
    }

    function severityIcon(severity) {
        switch (severity) {
            case 'contraindicated': return '🚫';
            case 'major': return '🔴';
            case 'moderate': return '🟡';
            case 'minor': return '🟢';
            default: return 'ℹ️';
        }
    }

    function formatAlertType(type) {
        return type.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
    }

    function renderSource(source) {
        if (!source) return '';
        return `<div class="alert-source">
            📄 ${source.authority} — ${source.document_title} (${source.publication_year || ''})
            ${source.url ? `<a href="${source.url}" target="_blank" rel="noopener" class="source-link">View ↗</a>` : ''}
        </div>`;
    }

    function updateWarningsPanel(data) {
        const panel = document.getElementById('panel-warnings');
        if (!panel) return;

        const allAlerts = [
            ...(data.interaction_alerts || []),
            ...(data.context_alerts || []),
        ];

        if (allAlerts.length === 0) {
            panel.innerHTML = '<p class="placeholder">No active warnings.</p>';
            return;
        }

        panel.innerHTML = allAlerts.map(a => `
            <div style="margin-bottom:8px;font-size:12px;">
                <strong>${a.drug_a || a.drug || ''} ${a.drug_b ? '+ ' + a.drug_b : ''}</strong>
                <span class="drug-tag">${a.severity || a.alert_type || ''}</span>
            </div>
        `).join('');
    }

    return { render };
})();
