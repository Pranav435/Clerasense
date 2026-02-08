/**
 * Clerasense – Ask More (Chat) Module
 * Natural language chatbot for follow-up drug queries,
 * pricing questions, comparisons, and general drug intelligence.
 */

const AskMoreModule = (() => {
    let messages = [];

    function render(container) {
        container.innerHTML = `
            <div class="chat-container">
                <div class="chat-header">
                    <h2>Ask More</h2>
                    <p>Ask any drug-related question in plain language.
                       All answers are sourced from verified regulatory data.</p>
                </div>
                <div class="disclaimer-banner">
                    This is an information-retrieval tool only. Responses are based on verified regulatory sources.
                    It does not provide diagnoses, treatment recommendations, or prescriptions.
                </div>
                <div class="chat-messages" id="chat-messages"></div>
                <div class="chat-input-area">
                    <input type="text" id="chat-input"
                           placeholder="Ask anything about a drug — e.g., &quot;Tell me about Metformin&quot;"
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

        // Build conversation history for context (exclude the loading message)
        const history = messages
            .filter(m => m.id !== loadingId && (m.type === 'user' || m.type === 'assistant'))
            .slice(-20)  // keep last 20 messages for context window
            .map(m => ({ role: m.type === 'user' ? 'user' : 'assistant', content: m.rawContent || stripHtml(m.content) }));

        const data = await API.chat(query, history);

        removeMessage(loadingId);

        if (data.error) {
            addMessage('assistant', `Error: ${data.error}`);
            return;
        }

        if (data.refused) {
            addMessage('refusal', data.response, data.response);
        } else {
            addMessage('assistant', formatResponse(data.response), data.response);
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

    function stripHtml(html) {
        const tmp = document.createElement('div');
        tmp.innerHTML = html;
        return tmp.textContent || tmp.innerText || '';
    }

    function addMessage(type, content, rawContent) {
        const id = 'msg-' + Date.now() + '-' + Math.random().toString(36).substr(2, 5);
        messages.push({ id, type, content, rawContent: rawContent || null });
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
                    <h3>Ask More — Drug Intelligence Chatbot</h3>
                    <p>Ask questions about medications in natural language.
                       I can help with drug details, interactions, dosages, safety profiles,
                       pricing, and comparisons.</p>
                    <p style="margin-top:12px;font-size:12px;color:var(--text-muted);">
                        Try: "Tell me about Atorvastatin" &bull; "What are the side effects of Metformin?"
                        &bull; "Compare Lisinopril vs Losartan" &bull; "Is it safe to combine aspirin and ibuprofen?"
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
