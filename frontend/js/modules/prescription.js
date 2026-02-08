/**
 * Clerasense – Prescription Verifier Module
 * Upload a prescription image/document, OCR it with Tesseract.js,
 * then verify medications against the drug database using AI analysis.
 *
 * OCR: Tesseract.js (free, no API key, runs in-browser)
 * PDF: pdf.js (for extracting text from PDF documents)
 * AI:  OpenAI via backend (already configured)
 *
 * This is an INFORMATION tool — NOT a clinical approval system.
 */

const PrescriptionVerifierModule = (() => {

    let _ocrWorker = null;

    /* ────────────────────────── render ────────────────────────── */

    function render(container) {
        container.innerHTML = `
            <div class="prescription-container">
                <div class="chat-header">
                    <h2>Prescription Verifier</h2>
                    <p>Upload a prescription image or document to verify medications, dosages, interactions, and safety.</p>
                </div>

                <div class="disclaimer-banner">
                    ⚠️ DISCLAIMER: This tool provides informational verification using data from
                    verified regulatory sources (FDA, NIH/NLM, DailyMed, FAERS) and AI analysis.
                    It is NOT a substitute for clinical judgment. The prescribing physician is solely
                    responsible for all prescribing and clinical decisions.
                </div>

                <!-- Upload Section -->
                <div class="rx-upload-section">
                    <div class="rx-upload-zone" id="upload-zone">
                        <div class="rx-upload-icon">📋</div>
                        <h3>Upload Prescription</h3>
                        <p>Drag &amp; drop an image or PDF here, or click to browse</p>
                        <p class="rx-upload-formats">Supported formats: JPG, PNG, BMP, GIF, PDF</p>
                        <input type="file" id="rx-file-input"
                               accept="image/jpeg,image/png,image/bmp,image/gif,application/pdf"
                               hidden>
                    </div>

                    <!-- Preview -->
                    <div id="rx-preview" class="rx-preview" style="display:none;">
                        <div class="rx-preview-header">
                            <span id="rx-file-name" class="rx-file-name"></span>
                            <button id="rx-clear-btn" class="btn btn-outline btn-small">✕ Clear</button>
                        </div>
                        <div id="rx-preview-img" class="rx-preview-img"></div>
                    </div>
                </div>

                <!-- OR divider -->
                <div class="rx-or-divider"><span>OR</span></div>

                <!-- Manual text entry / OCR result -->
                <div class="rx-text-section">
                    <label for="rx-text">Paste or edit prescription text</label>
                    <textarea id="rx-text" rows="8"
                              placeholder="You can also paste prescription text directly here…"></textarea>
                </div>

                <!-- OCR Progress -->
                <div id="rx-ocr-progress" class="rx-ocr-progress" style="display:none;">
                    <div class="rx-progress-bar-track">
                        <div class="rx-progress-bar-fill" id="rx-progress-fill"></div>
                    </div>
                    <p id="rx-ocr-status" class="rx-ocr-status">Initializing OCR engine…</p>
                </div>

                <!-- Verify button -->
                <div class="rx-actions">
                    <button id="rx-verify-btn" class="btn btn-primary" disabled>
                        🔍 Verify Prescription
                    </button>
                </div>

                <!-- Results -->
                <div id="rx-results"></div>
            </div>
        `;

        /* event wiring */
        const zone   = document.getElementById('upload-zone');
        const fInput = document.getElementById('rx-file-input');

        zone.addEventListener('click', () => fInput.click());
        zone.addEventListener('dragover', onDragOver);
        zone.addEventListener('dragleave', onDragLeave);
        zone.addEventListener('drop', onDrop);
        fInput.addEventListener('change', onFileSelected);

        document.getElementById('rx-clear-btn').addEventListener('click', clearUpload);
        document.getElementById('rx-text').addEventListener('input', onTextInput);
        document.getElementById('rx-verify-btn').addEventListener('click', verifyPrescription);
    }

    /* ────────────────────── drag / drop handlers ─────────────── */

    function onDragOver(e) {
        e.preventDefault();
        e.currentTarget.classList.add('rx-drag-active');
    }

    function onDragLeave(e) {
        e.currentTarget.classList.remove('rx-drag-active');
    }

    function onDrop(e) {
        e.preventDefault();
        e.currentTarget.classList.remove('rx-drag-active');
        const file = e.dataTransfer.files[0];
        if (file) processFile(file);
    }

    function onFileSelected(e) {
        const file = e.target.files[0];
        if (file) processFile(file);
    }

    function onTextInput() {
        const btn = document.getElementById('rx-verify-btn');
        btn.disabled = !document.getElementById('rx-text').value.trim();
    }

    function clearUpload() {
        document.getElementById('rx-preview').style.display = 'none';
        document.getElementById('rx-preview-img').innerHTML = '';
        document.getElementById('rx-file-input').value = '';
        document.getElementById('rx-text').value = '';
        document.getElementById('rx-verify-btn').disabled = true;
        document.getElementById('rx-results').innerHTML = '';
        document.getElementById('rx-ocr-progress').style.display = 'none';
    }

    /* ───────────────────── file processing ────────────────────── */

    async function processFile(file) {
        const preview = document.getElementById('rx-preview');
        const nameEl  = document.getElementById('rx-file-name');
        const imgBox  = document.getElementById('rx-preview-img');

        nameEl.textContent = file.name;
        preview.style.display = 'block';

        if (file.type === 'application/pdf') {
            imgBox.innerHTML = '<div class="rx-pdf-badge">📄 PDF Document</div>';
            await processPDF(file);
        } else {
            // Image preview
            const url = URL.createObjectURL(file);
            imgBox.innerHTML = `<img src="${url}" alt="Prescription image" style="max-width:100%;max-height:400px;border-radius:6px;">`;
            await processImage(file);
        }
    }

    /* ───────────────── PDF processing (pdf.js) ────────────────── */

    async function processPDF(file) {
        showOCRProgress('Loading PDF…', 0);

        try {
            const arrayBuffer = await file.arrayBuffer();

            // Configure pdf.js worker
            if (typeof pdfjsLib !== 'undefined') {
                pdfjsLib.GlobalWorkerOptions.workerSrc =
                    'https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.worker.min.js';
            }

            const pdf = await pdfjsLib.getDocument({ data: arrayBuffer }).promise;

            // Try native text extraction first (works for digital PDFs)
            let extracted = '';
            for (let i = 1; i <= pdf.numPages; i++) {
                showOCRProgress(`Extracting text from page ${i}/${pdf.numPages}…`, (i - 1) / pdf.numPages * 0.3);
                const page = await pdf.getPage(i);
                const content = await page.getTextContent();
                extracted += content.items.map(item => item.str).join(' ') + '\n';
            }

            // If we got meaningful text, use it directly (no OCR needed)
            if (extracted.trim().length > 30) {
                showOCRProgress('Text extracted from PDF successfully.', 1);
                document.getElementById('rx-text').value = extracted.trim();
                document.getElementById('rx-verify-btn').disabled = false;
                setTimeout(() => hideOCRProgress(), 1500);
                return;
            }

            // Scanned PDF — render pages to canvas and OCR each
            showOCRProgress('Scanned PDF detected. Running OCR…', 0.3);
            let ocrText = '';
            for (let i = 1; i <= pdf.numPages; i++) {
                showOCRProgress(`OCR on page ${i}/${pdf.numPages}…`, 0.3 + (i - 1) / pdf.numPages * 0.7);
                const page = await pdf.getPage(i);
                const viewport = page.getViewport({ scale: 2.0 });  // Higher scale = better OCR
                const canvas = document.createElement('canvas');
                canvas.width = viewport.width;
                canvas.height = viewport.height;
                const ctx = canvas.getContext('2d');
                await page.render({ canvasContext: ctx, viewport }).promise;

                const result = await runOCR(canvas);
                ocrText += result + '\n';
            }

            document.getElementById('rx-text').value = ocrText.trim();
            document.getElementById('rx-verify-btn').disabled = !ocrText.trim();
            showOCRProgress('OCR complete.', 1);
            setTimeout(() => hideOCRProgress(), 1500);

        } catch (err) {
            console.error('PDF processing failed:', err);
            showOCRProgress('PDF processing failed. Please paste text manually.', 0);
            document.getElementById('rx-ocr-status').style.color = '#c0392b';
        }
    }

    /* ───────────────── image OCR (Tesseract.js) ───────────────── */

    async function processImage(file) {
        showOCRProgress('Initializing OCR engine…', 0);

        try {
            const result = await runOCR(file);
            document.getElementById('rx-text').value = result;
            document.getElementById('rx-verify-btn').disabled = !result.trim();
            showOCRProgress('OCR complete.', 1);
            setTimeout(() => hideOCRProgress(), 1500);
        } catch (err) {
            console.error('OCR failed:', err);
            showOCRProgress('OCR failed. Please paste text manually.', 0);
            document.getElementById('rx-ocr-status').style.color = '#c0392b';
        }
    }

    async function runOCR(input) {
        if (!_ocrWorker) {
            _ocrWorker = await Tesseract.createWorker('eng', 1, {
                logger: m => {
                    if (m.status === 'recognizing text') {
                        showOCRProgress('Recognizing text…', 0.2 + m.progress * 0.8);
                    } else if (m.status) {
                        showOCRProgress(m.status + '…', Math.min(m.progress || 0, 0.2));
                    }
                }
            });
        }
        const { data: { text } } = await _ocrWorker.recognize(input);
        return text.trim();
    }

    /* ───────────────── progress helpers ───────────────────────── */

    function showOCRProgress(msg, fraction) {
        const wrap = document.getElementById('rx-ocr-progress');
        const fill = document.getElementById('rx-progress-fill');
        const stat = document.getElementById('rx-ocr-status');

        wrap.style.display = 'block';
        fill.style.width = Math.round(fraction * 100) + '%';
        stat.textContent = msg;
        stat.style.color = '';
    }

    function hideOCRProgress() {
        document.getElementById('rx-ocr-progress').style.display = 'none';
    }

    /* ───────────────── verification ───────────────────────────── */

    async function verifyPrescription() {
        const text = document.getElementById('rx-text').value.trim();
        if (!text) return;

        const resultsEl = document.getElementById('rx-results');
        resultsEl.innerHTML = `
            <div class="loading">
                Verifying prescription against drug database & AI analysis…<br>
                <small>This may take a moment.</small>
            </div>`;

        document.getElementById('rx-verify-btn').disabled = true;

        try {
            const data = await API.verifyPrescription(text);
            document.getElementById('rx-verify-btn').disabled = false;

            if (data.error) {
                resultsEl.innerHTML = `<div class="alert-card severity-major">
                    <div class="alert-title">⚠️ Verification Error</div>
                    <p>${data.error}</p>
                </div>`;
                return;
            }

            renderVerificationResults(data, resultsEl);
            updateWarningsPanel(data);

        } catch (err) {
            document.getElementById('rx-verify-btn').disabled = false;
            resultsEl.innerHTML = `<div class="alert-card severity-major">
                <div class="alert-title">⚠️ Error</div>
                <p>An error occurred during verification. Please try again.</p>
            </div>`;
        }
    }

    /* ═══════════════════ RESULTS RENDERING ═══════════════════════ */

    function renderVerificationResults(data, container) {
        let html = '';
        const ai = data.ai_analysis || {};

        // ── 1. Overall Assessment Banner ──
        html += renderAssessmentBadge(ai);

        // ── 2. Extracted Prescription Summary (collapsed by default) ──
        html += renderExtractedInfo(data.extracted_data || {});

        // ── 3. Drugs Not Found ──
        if (data.drugs_not_found && data.drugs_not_found.length) {
            html += `<div class="alert-card severity-moderate">
                <div class="alert-title">⚠️ Not Found in Database</div>
                <p><strong>${data.drugs_not_found.join(', ')}</strong> — could not be verified.
                   May be misspelled, brand-only, or not yet ingested.</p>
            </div>`;
        }

        // ── 4. Per-Medication Clinical Cards (main content) ──
        if (ai.medication_analysis && ai.medication_analysis.length) {
            html += renderMedicationCards(ai.medication_analysis, data);
        }

        // ── 5. Interaction Alerts (DB-sourced, highest trust) ──
        if (data.interaction_alerts && data.interaction_alerts.length) {
            html += renderInteractionAlerts(data.interaction_alerts);
        }

        // ── 6. AI Interaction Alerts (cross-referenced) ──
        if (ai.interaction_alerts && ai.interaction_alerts.length) {
            html += renderAIInteractions(ai.interaction_alerts);
        }

        // ── 7. Required Scans & Tests (action-oriented) ──
        if (ai.required_scans_and_tests && ai.required_scans_and_tests.length) {
            html += renderRequiredTests(ai.required_scans_and_tests);
        }

        // ── 8. Missing Info & Recommendations (brief) ──
        if ((ai.missing_information && ai.missing_information.length) ||
            (ai.recommendations && ai.recommendations.length)) {
            html += renderActionItems(ai.missing_information || [], ai.recommendations || []);
        }

        // ── 9. Disclaimer ──
        if (data.disclaimer) {
            html += `<div class="disclaimer-banner" style="margin-top:24px;">${data.disclaimer}</div>`;
        }

        container.innerHTML = html;
    }

    /* ── Assessment Badge ── */
    function renderAssessmentBadge(ai) {
        const assessment = ai.overall_assessment || 'UNKNOWN';
        const summary = ai.assessment_summary || '';
        const badges = {
            'VERIFIED':              { cls: 'rx-badge-ok',     icon: '✅', label: 'Verified' },
            'VERIFIED WITH CONCERNS':{ cls: 'rx-badge-warn',   icon: '⚠️', label: 'Verified with Concerns' },
            'REQUIRES REVIEW':       { cls: 'rx-badge-danger', icon: '🔴', label: 'Requires Review' },
        };
        const b = badges[assessment] || { cls: 'rx-badge-warn', icon: 'ℹ️', label: assessment };
        return `<div class="rx-assessment ${b.cls}">
            <div class="rx-assessment-icon">${b.icon}</div>
            <div class="rx-assessment-body">
                <div class="rx-assessment-label">${b.label}</div>
                ${summary ? `<p class="rx-assessment-summary">${summary}</p>` : ''}
            </div>
        </div>`;
    }

    /* ── Extracted Prescription (collapsible) ── */
    function renderExtractedInfo(ex) {
        const meds = ex.medications || [];
        const patient = ex.patient_info || {};
        if (!meds.length) return '';

        const infoChips = [];
        if (patient.name)  infoChips.push(`<span class="rx-chip">👤 ${patient.name}</span>`);
        if (patient.age)   infoChips.push(`<span class="rx-chip">${patient.age}</span>`);
        if (patient.gender) infoChips.push(`<span class="rx-chip">${patient.gender}</span>`);
        if (ex.prescriber) infoChips.push(`<span class="rx-chip">🩺 ${ex.prescriber}</span>`);
        if (ex.date)       infoChips.push(`<span class="rx-chip">📅 ${ex.date}</span>`);
        if (ex.diagnosis)  infoChips.push(`<span class="rx-chip rx-chip-dx">Dx: ${ex.diagnosis}</span>`);

        let html = `<details class="rx-extract-details" open>
            <summary class="rx-section-bar">📋 Extracted Prescription Data</summary>
            <div class="rx-extract-body">`;

        if (infoChips.length) html += `<div class="rx-chip-row">${infoChips.join('')}</div>`;

        if (meds.length) {
            html += `<table class="rx-med-table"><thead><tr>
                <th>Medication</th><th>Dose</th><th>Freq</th><th>Route</th><th>Duration</th>
            </tr></thead><tbody>`;
            meds.forEach(m => {
                html += `<tr>
                    <td><strong>${m.drug_name || '—'}</strong></td>
                    <td>${m.dosage || '—'}</td>
                    <td>${m.frequency || '—'}</td>
                    <td>${m.route || '—'}</td>
                    <td>${m.duration || '—'}</td>
                </tr>`;
            });
            html += '</tbody></table>';
        }
        if (ex.additional_instructions) {
            html += `<p class="rx-add-instr"><strong>Instructions:</strong> ${ex.additional_instructions}</p>`;
        }
        html += '</div></details>';
        return html;
    }

    /* ═══ Per-Medication Clinical Cards ═══ */
    function renderMedicationCards(meds, data) {
        let html = '<h3 class="section-heading">💊 Medication Verification</h3>';

        meds.forEach(m => {
            const found = m.found_in_database;
            const dv = m.dosage_verdict || {};
            const iv = m.indication_verdict || {};

            // choose card border color
            const borderCls = !found                       ? 'rx-card-unknown'
                            : (dv.status === 'APPROPRIATE' && iv.status === 'APPROPRIATE') ? 'rx-card-ok'
                            : (dv.status === 'HIGH' || dv.status === 'LOW' || iv.status === 'NOT INDICATED') ? 'rx-card-danger'
                            : 'rx-card-warn';

            html += `<div class="rx-drug-card ${borderCls}">`;

            // ── header ──
            html += `<div class="rx-drug-header">
                <div class="rx-drug-name">${m.drug_name}${m.drug_class ? ` <span class="rx-drug-class">${m.drug_class}</span>` : ''}</div>
                ${!found ? '<span class="rx-status-chip rx-chip-unknown">Not in DB</span>' : ''}
            </div>`;

            if (!found) {
                html += `<div class="rx-row rx-row-muted"><em>Not found in verified database — verification limited.</em></div>`;
                html += '</div>';
                return;
            }

            // ── Dosage Row ──
            html += `<div class="rx-field-row">
                <div class="rx-field-label">Dosage</div>
                <div class="rx-field-content">
                    <div class="rx-field-flex">
                        <span class="rx-prescribed">Prescribed: <strong>${m.prescribed_dosage || '—'}</strong></span>
                        ${statusChip(dv.status)}
                    </div>
                    ${dv.standard_range ? `<div class="rx-field-detail">Standard range: ${dv.standard_range}</div>` : ''}
                    ${dv.note ? `<div class="rx-field-detail">${dv.note}</div>` : ''}
                    ${renderInlineSource(dv.source)}
                </div>
            </div>`;

            // ── Indication Row ──
            html += `<div class="rx-field-row">
                <div class="rx-field-label">Indication</div>
                <div class="rx-field-content">
                    <div class="rx-field-flex">
                        <span>${iv.approved_uses || '—'}</span>
                        ${statusChip(iv.status)}
                    </div>
                    ${iv.note ? `<div class="rx-field-detail">${iv.note}</div>` : ''}
                    ${renderInlineSource(iv.source)}
                </div>
            </div>`;

            // ── Black Box Warning ──
            if (m.black_box_warning) {
                html += `<div class="rx-bbw">
                    <div class="rx-bbw-label">⛔ BLACK BOX WARNING</div>
                    <div class="rx-bbw-text">${truncate(m.black_box_warning, 600)}</div>
                </div>`;
            }

            // ── Contraindications ──
            if (m.contraindications_summary) {
                html += `<div class="rx-field-row">
                    <div class="rx-field-label">🚫 Contraindications</div>
                    <div class="rx-field-content">${m.contraindications_summary}</div>
                </div>`;
            }

            // ── Key Warnings (with per-warning source) ──
            if (m.key_warnings && m.key_warnings.length) {
                html += `<div class="rx-field-row">
                    <div class="rx-field-label">⚠️ Warnings</div>
                    <div class="rx-field-content"><ul class="rx-compact-list">`;
                m.key_warnings.forEach(w => {
                    const wText = typeof w === 'string' ? w : w.text;
                    const wSrc  = typeof w === 'string' ? null : w.source;
                    html += `<li>${wText}${wSrc ? ` <span class="rx-inline-src">[${wSrc}]</span>` : ''}</li>`;
                });
                html += `</ul></div></div>`;
            }

            // ── Monitoring ──
            if (m.monitoring && m.monitoring.length) {
                html += `<div class="rx-field-row">
                    <div class="rx-field-label">🔬 Monitoring</div>
                    <div class="rx-field-content"><table class="rx-mini-table"><thead><tr>
                        <th>Test</th><th>Timing</th><th>Reason</th>
                    </tr></thead><tbody>`;
                m.monitoring.forEach(t => {
                    html += `<tr>
                        <td><strong>${t.test || '—'}</strong></td>
                        <td>${t.timing || '—'}</td>
                        <td>${t.reason || '—'}</td>
                    </tr>`;
                });
                html += '</tbody></table></div></div>';
            }

            // ── Dosage Instructions ──
            if (m.dosage_instructions) {
                html += `<div class="rx-field-row">
                    <div class="rx-field-label">📝 Instructions</div>
                    <div class="rx-field-content">${m.dosage_instructions}</div>
                </div>`;
            }

            // ── Renal / Hepatic ──
            if (m.renal_adjustment || m.hepatic_adjustment) {
                html += `<div class="rx-field-row">
                    <div class="rx-field-label">👥 Adjustments</div>
                    <div class="rx-field-content">`;
                if (m.renal_adjustment)   html += `<div><strong>Renal:</strong> ${m.renal_adjustment}</div>`;
                if (m.hepatic_adjustment) html += `<div><strong>Hepatic:</strong> ${m.hepatic_adjustment}</div>`;
                html += '</div></div>';
            }

            // ── Pregnancy ──
            if (m.pregnancy_risk) {
                html += `<div class="rx-field-row">
                    <div class="rx-field-label">🤰 Pregnancy</div>
                    <div class="rx-field-content">${m.pregnancy_risk}</div>
                </div>`;
            }

            // ── DB Safety Warning source + FAERS inline ──
            const dbWarning = (data.safety_warnings || []).find(w => w.drug && w.drug.toLowerCase() === m.drug_name.toLowerCase());
            if (dbWarning) {
                html += renderFAERSInline(dbWarning);
                html += `<div class="rx-db-source-row">${renderSourceBadge(dbWarning.source)}</div>`;
            }

            // ── DB Dosage Guidelines source ──
            const dbDosage = (data.dosage_guidelines || {})[m.drug_name];
            if (dbDosage && dbDosage.length) {
                dbDosage.forEach(dg => {
                    html += `<div class="rx-db-source-row">${renderSourceBadge(dg.source)}</div>`;
                });
            }

            html += '</div>'; // end rx-drug-card
        });
        return html;
    }

    /* ── Interaction Alerts (DB-sourced) ── */
    function renderInteractionAlerts(alerts) {
        let html = '<h3 class="section-heading">⚡ Drug-Drug Interactions <span class="rx-section-tag">Database-verified</span></h3>';
        alerts.forEach(a => {
            html += `<div class="alert-card severity-${a.severity}">
                <div class="alert-title">
                    ${severityIcon(a.severity)} ${a.drug_a} + ${a.drug_b}
                    <span class="drug-tag">${(a.severity || '').toUpperCase()}</span>
                </div>
                <p>${a.description}</p>
                ${renderSourceBadge(a.source)}
            </div>`;
        });
        return html;
    }

    /* ── AI Interaction Alerts ── */
    function renderAIInteractions(alerts) {
        let html = '<h3 class="section-heading">🔬 Additional Interaction Concerns <span class="rx-section-tag">AI-identified</span></h3>';
        alerts.forEach(a => {
            html += `<div class="alert-card severity-major">
                <div class="alert-title">⚠️ ${(a.drugs || []).join(' + ')}
                    ${a.severity ? `<span class="drug-tag">${a.severity.toUpperCase()}</span>` : ''}
                </div>
                <p>${a.description || ''}</p>
                ${a.clinical_action ? `<p class="rx-field-detail"><strong>Action:</strong> ${a.clinical_action}</p>` : ''}
                ${a.source ? `<span class="rx-inline-src">[${a.source}]</span>` : ''}
            </div>`;
        });
        return html;
    }

    /* ── Required Scans & Tests ── */
    function renderRequiredTests(tests) {
        let html = '<h3 class="section-heading">🏥 Required Monitoring &amp; Tests</h3>';
        html += '<table class="rx-tests-table"><thead><tr><th>Test</th><th>Timing</th><th>Reason</th><th>Drug</th></tr></thead><tbody>';
        tests.forEach(t => {
            html += `<tr>
                <td><strong>${t.test_name || '—'}</strong></td>
                <td>${t.timing || '—'}</td>
                <td>${t.reason || '—'}</td>
                <td>${t.related_drug || '—'}</td>
            </tr>`;
        });
        html += '</tbody></table>';
        return html;
    }

    /* ── Missing Info + Recommendations (combined) ── */
    function renderActionItems(missing, recs) {
        let html = '<div class="rx-action-columns">';
        if (missing.length) {
            html += `<div class="rx-action-col">
                <h4>📝 Missing from Prescription</h4>
                <ul>${missing.map(m => `<li>${m}</li>`).join('')}</ul>
            </div>`;
        }
        if (recs.length) {
            html += `<div class="rx-action-col">
                <h4>💡 Clinical Recommendations</h4>
                <ul>${recs.map(r => `<li>${r}</li>`).join('')}</ul>
            </div>`;
        }
        html += '</div>';
        return html;
    }

    /* ── FAERS inline (compact) ── */
    function renderFAERSInline(w) {
        const count = w.adverse_event_count;
        const serious = w.adverse_event_serious_count;
        const reactions = w.top_adverse_reactions || [];
        if (!count && !reactions.length) return '';

        let html = `<div class="rx-faers-row">
            <div class="rx-field-label">📊 FAERS</div>
            <div class="rx-field-content rx-faers-content">`;
        if (count) {
            const pct = serious && count ? ((serious / count) * 100).toFixed(1) : '—';
            html += `<div class="rx-faers-stats">
                <span><strong>${count.toLocaleString()}</strong> reports</span>
                <span class="rx-faers-sep">·</span>
                <span><strong>${serious ? serious.toLocaleString() : '—'}</strong> serious (${pct}%)</span>
            </div>`;
        }
        if (reactions.length) {
            html += `<div class="rx-faers-reactions">Top: ${reactions.slice(0, 5).map(r =>
                `${r.reaction} <span class="rx-faers-ct">(${r.count.toLocaleString()})</span>`
            ).join(', ')}</div>`;
        }
        html += `<span class="rx-inline-src">[FDA FAERS — <a href="https://open.fda.gov/apis/drug/event/" target="_blank" rel="noopener">open.fda.gov</a>]</span>`;
        html += '</div></div>';
        return html;
    }

    /* ═══ Helpers ═══ */

    function statusChip(status) {
        if (!status) return '';
        const map = {
            'APPROPRIATE':   { cls: 'rx-chip-ok',      label: '✓ Appropriate' },
            'HIGH':          { cls: 'rx-chip-danger',   label: '↑ Potentially High' },
            'LOW':           { cls: 'rx-chip-danger',   label: '↓ Potentially Low' },
            'NOT INDICATED': { cls: 'rx-chip-danger',   label: '✗ Not Indicated' },
            'UNVERIFIABLE':  { cls: 'rx-chip-unknown',  label: '? Unverifiable' },
        };
        const m = map[status] || { cls: 'rx-chip-unknown', label: status };
        return `<span class="rx-status-chip ${m.cls}">${m.label}</span>`;
    }

    function renderInlineSource(src) {
        if (!src) return '';
        return `<div class="rx-inline-src">[${src}]</div>`;
    }

    function renderSourceBadge(source) {
        if (!source) return '';
        const authority = source.authority || 'Unknown';
        const badgeColors = { 'FDA': '#1a5276', 'NIH/NLM': '#196f3d', 'CMS': '#7d3c98' };
        const color = badgeColors[authority] || '#555';
        const title = source.document_title || '';
        const year = source.publication_year || '';
        const url = source.url || '';
        const effDate = source.effective_date ? ` | Effective: ${source.effective_date}` : '';
        const retrieved = source.data_retrieved_at
            ? ` | Fetched: ${new Date(source.data_retrieved_at).toLocaleDateString()}`
            : '';

        return `<div class="rx-source-badge">
            <span class="rx-src-authority" style="background:${color}">${authority}</span>
            <span class="rx-src-detail">${title}${year ? ` (${year})` : ''}${effDate}${retrieved}</span>
            ${url ? `<a href="${url}" target="_blank" rel="noopener" class="rx-src-link" style="color:${color}">Verify ↗</a>` : ''}
        </div>`;
    }

    function severityIcon(severity) {
        switch (severity) {
            case 'contraindicated': return '🚫';
            case 'major':          return '🔴';
            case 'moderate':       return '🟡';
            case 'minor':          return '🟢';
            default:               return 'ℹ️';
        }
    }

    function truncate(str, max) {
        if (!str) return '';
        return str.length > max ? str.substring(0, max) + '…' : str;
    }

    function updateWarningsPanel(data) {
        const panel = document.getElementById('panel-warnings');
        if (!panel) return;
        const alerts = [...(data.interaction_alerts || [])];
        const ai = data.ai_analysis || {};
        if (ai.medication_analysis) {
            ai.medication_analysis.forEach(m => {
                const dv = m.dosage_verdict || {};
                if (dv.status && dv.status !== 'APPROPRIATE' && dv.status !== 'UNVERIFIABLE') {
                    alerts.push({ warning: `${m.drug_name}: dosage ${dv.status.toLowerCase()}` });
                }
            });
        }
        if (!alerts.length) { panel.innerHTML = '<p class="placeholder">No active warnings.</p>'; return; }
        panel.innerHTML = alerts.map(a => {
            if (a.warning) return `<div style="margin-bottom:8px;font-size:12px;">⚠️ ${a.warning}</div>`;
            return `<div style="margin-bottom:8px;font-size:12px;">
                <strong>${a.drug_a || ''} ${a.drug_b ? '+ ' + a.drug_b : ''}</strong>
                <span class="drug-tag">${a.severity || ''}</span>
            </div>`;
        }).join('');
    }

    return { render };
})();
