/**
 * Clerasense – Safety Checker Module
 * Enhanced with real-time adverse event data (FDA FAERS)
 * and detailed per-field source attribution.
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
                    ⚠️ DISCLAIMER: This tool provides informational alerts from verified regulatory sources
                    (FDA, NIH/NLM, CMS NADAC, FDA FAERS).
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
        resultsEl.innerHTML = '<div class="loading">Checking safety across FDA, DailyMed, FAERS & NADAC… may take a moment for new drugs.</div>';

        const data = await API.checkSafety(drugNames, context);

        if (data.error) {
            resultsEl.innerHTML = `<p class="error-msg">${data.error}</p>`;
            return;
        }

        renderSafetyResults(data, resultsEl);
    }

    function renderSourceBadge(source) {
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
        const effDate = source.effective_date ? ` | Label effective: ${source.effective_date}` : '';
        const retrieved = source.data_retrieved_at
            ? ` | Fetched: ${new Date(source.data_retrieved_at).toLocaleDateString()}`
            : '';

        return `<div class="source-attribution" style="margin-top:8px;padding:6px 10px;background:#f8f9fa;border-left:3px solid ${color};border-radius:4px;font-size:11px;line-height:1.4;">
            <span style="display:inline-block;padding:1px 6px;background:${color};color:#fff;border-radius:3px;font-size:10px;font-weight:600;margin-right:6px;">${authority}</span>
            <span>${title} (${year}${effDate}${retrieved})</span>
            ${url ? ` <a href="${url}" target="_blank" rel="noopener" style="color:${color};margin-left:6px;">Verify Source ↗</a>` : ''}
        </div>`;
    }

    function renderAdverseEvents(warning) {
        const count = warning.adverse_event_count;
        const serious = warning.adverse_event_serious_count;
        const reactions = warning.top_adverse_reactions || [];

        if (count === null && count === undefined && !reactions.length) return '';
        if (!count && !reactions.length) return '';

        let html = '<div style="margin-top:12px;padding:10px;background:#fdf2e9;border-radius:6px;">';
        html += '<strong style="font-size:13px;">📊 FDA Adverse Event Reports (FAERS – Real-Time)</strong>';

        if (count !== null && count !== undefined) {
            const seriousPct = serious && count ? ((serious / count) * 100).toFixed(1) : '—';
            html += `<div style="display:flex;gap:20px;margin:8px 0;flex-wrap:wrap;">
                <div style="text-align:center;">
                    <div style="font-size:18px;font-weight:700;color:#e67e22;">${count.toLocaleString()}</div>
                    <div style="font-size:10px;color:#666;">Total Reports</div>
                </div>
                <div style="text-align:center;">
                    <div style="font-size:18px;font-weight:700;color:#c0392b;">${serious ? serious.toLocaleString() : '—'}</div>
                    <div style="font-size:10px;color:#666;">Serious Reports</div>
                </div>
                <div style="text-align:center;">
                    <div style="font-size:18px;font-weight:700;color:#c0392b;">${seriousPct}%</div>
                    <div style="font-size:10px;color:#666;">Serious Rate</div>
                </div>
            </div>`;
        }

        if (reactions.length) {
            html += '<div style="margin-top:6px;"><strong style="font-size:11px;">Top Reported Reactions:</strong><ul style="margin:4px 0;padding-left:18px;">';
            for (const r of reactions.slice(0, 10)) {
                html += `<li style="font-size:11px;margin:2px 0;">${r.reaction} <span style="color:#888;">(${r.count.toLocaleString()} reports)</span></li>`;
            }
            html += '</ul></div>';
        }

        html += `<div style="font-size:10px;color:#888;margin-top:4px;">Source: FDA Adverse Event Reporting System (FAERS) — real-time data from <a href="https://open.fda.gov/apis/drug/event/" target="_blank" rel="noopener">open.fda.gov</a></div>`;
        html += '</div>';
        return html;
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
                        ${renderSourceBadge(alert.source)}
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
                        ${renderSourceBadge(alert.source)}
                    </div>
                `;
            });
        }

        // Safety warnings per drug
        if (data.safety_warnings && data.safety_warnings.length) {
            html += '<h3 class="section-heading">Safety Warnings</h3>';
            data.safety_warnings.forEach(w => {
                html += `<div class="alert-card severity-moderate">`;
                html += `<div class="alert-title">⚕️ ${w.drug}</div>`;

                if (w.black_box_warnings) {
                    html += `<div style="background:#fdedec;border:1px solid #e74c3c;border-radius:4px;padding:8px;margin:8px 0;">
                        <strong style="color:#c0392b;">⛔ BLACK BOX WARNING</strong>
                        <p style="margin:4px 0;font-size:12px;">${truncate(w.black_box_warnings, 800)}</p>
                    </div>`;
                }

                if (w.contraindications) {
                    html += `<p><strong>🚫 Contraindications:</strong> ${truncate(w.contraindications, 800)}</p>`;
                }
                if (w.pregnancy_risk) {
                    html += `<p><strong>🤰 Pregnancy:</strong> ${truncate(w.pregnancy_risk, 500)}</p>`;
                }
                if (w.lactation_risk) {
                    html += `<p><strong>🍼 Lactation:</strong> ${truncate(w.lactation_risk, 500)}</p>`;
                }

                // Adverse events from FAERS (new!)
                html += renderAdverseEvents(w);

                // Source attribution with badges
                html += renderSourceBadge(w.source);
                html += `</div>`;
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

    function truncate(str, max) {
        if (!str) return '';
        return str.length > max ? str.substring(0, max) + '…' : str;
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
