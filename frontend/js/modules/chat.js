/**
 * Clerasense – Drug Info Chat Module
 * Natural language drug information chat with RAG-backed responses.
 */

const ChatModule = (() => {
    let messages = [];

    function render(container) {
        container.innerHTML = `
            <div class="chat-container">
                <div class="chat-header">
                    <h2>Drug Information Chat</h2>
                    <p>Ask about drug indications, dosages, safety profiles, interactions, and more.
                       All answers are sourced from verified regulatory data.</p>
                </div>
                <div class="disclaimer-banner">
                    This is an information-retrieval tool only. Responses are based on verified regulatory sources.
                    It does not provide diagnoses, treatment recommendations, or prescriptions.
                </div>
                <div class="chat-messages" id="chat-messages"></div>
                <div class="chat-input-area">
                    <input type="text" id="chat-input"
                           placeholder="e.g., What are the contraindications for Metformin?"
                           autocomplete="off">
                    <button id="chat-send" class="btn btn-primary" style="width:auto;">Send</button>
                </div>
            </div>
        `;

        const input = document.getElementById('chat-input');
        const sendBtn = document.getElementById('chat-send');

        sendBtn.addEventListener('click', () => sendMessage(input));
        input.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') sendMessage(input);
        });

        renderMessages();
    }

    async function sendMessage(input) {
        const query = input.value.trim();
        if (!query) return;

        input.value = '';
        addMessage('user', query);

        // Show loading
        const loadingId = addMessage('assistant', '<div class="loading">Retrieving information…</div>');

        const data = await API.chat(query);

        removeMessage(loadingId);

        if (data.error) {
            addMessage('assistant', `Error: ${data.error}`);
            return;
        }

        if (data.refused) {
            addMessage('refusal', data.response);
        } else {
            addMessage('assistant', formatResponse(data.response));
            updateContextPanel(data.sources || []);
        }
    }

    function formatResponse(text) {
        // Basic markdown rendering
        return text
            .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
            .replace(/\n/g, '<br>')
            .replace(/• /g, '&bull; ')
            .replace(/\[Source: (.*?)\]/g, '<span class="source-citation">📄 $1</span>');
    }

    function addMessage(type, content) {
        const id = 'msg-' + Date.now() + '-' + Math.random().toString(36).substr(2, 5);
        messages.push({ id, type, content });
        renderMessages();
        return id;
    }

    function removeMessage(id) {
        messages = messages.filter(m => m.id !== id);
        renderMessages();
    }

    function renderMessages() {
        const container = document.getElementById('chat-messages');
        if (!container) return;

        if (messages.length === 0) {
            container.innerHTML = `
                <div class="empty-state">
                    <h3>Drug Information Assistant</h3>
                    <p>Ask about any drug's approved uses, dosage guidelines, safety warnings,
                       drug interactions, or regulatory information.</p>
                    <p style="margin-top:12px;font-size:12px;color:var(--text-muted);">
                        Example: "What are the safety warnings for Atorvastatin?"
                    </p>
                </div>
            `;
            return;
        }

        container.innerHTML = messages.map(m => `
            <div class="chat-message ${m.type}" id="${m.id}">
                ${m.content}
            </div>
        `).join('');

        container.scrollTop = container.scrollHeight;
    }

    function updateContextPanel(sources) {
        const panel = document.getElementById('panel-sources');
        if (!panel || !sources.length) return;

        panel.innerHTML = sources.map(s => `
            <div style="margin-bottom:10px;">
                <div style="font-weight:600;font-size:12px;">${s.authority}</div>
                <div style="font-size:12px;color:var(--text-secondary);">${s.document_title}</div>
                <div style="font-size:11px;color:var(--text-muted);">${s.publication_year || ''}</div>
                ${s.url ? `<a href="${s.url}" target="_blank" rel="noopener" class="source-link">View source ↗</a>` : ''}
            </div>
        `).join('');
    }

    function reset() {
        messages = [];
    }

    return { render, reset };
})();
