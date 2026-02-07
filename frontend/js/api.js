/**
 * Clerasense – API Client
 * Centralized HTTP client for all backend communication.
 * Handles token injection, error handling, and response parsing.
 * NEVER stores API keys – authentication is token-based only.
 */

const API = (() => {
    const BASE_URL = '/api';

    function getToken() {
        return localStorage.getItem('clerasense_token');
    }

    function setToken(token) {
        localStorage.setItem('clerasense_token', token);
    }

    function clearToken() {
        localStorage.removeItem('clerasense_token');
        localStorage.removeItem('clerasense_doctor');
    }

    function setDoctor(doctor) {
        localStorage.setItem('clerasense_doctor', JSON.stringify(doctor));
    }

    function getDoctor() {
        try {
            return JSON.parse(localStorage.getItem('clerasense_doctor'));
        } catch {
            return null;
        }
    }

    async function request(endpoint, options = {}) {
        const url = `${BASE_URL}${endpoint}`;
        const headers = {
            'Content-Type': 'application/json',
            ...options.headers,
        };

        const token = getToken();
        if (token) {
            headers['Authorization'] = `Bearer ${token}`;
        }

        try {
            const response = await fetch(url, {
                ...options,
                headers,
            });

            const data = await response.json();

            if (response.status === 401) {
                clearToken();
                window.location.reload();
                return { error: 'Session expired. Please log in again.' };
            }

            if (!response.ok) {
                return { error: data.error || `Request failed (${response.status})` };
            }

            return data;
        } catch (err) {
            console.error('API Error:', err);
            return { error: 'Network error. Please check your connection.' };
        }
    }

    // ── Auth ──
    async function login(email, password) {
        const data = await request('/auth/login', {
            method: 'POST',
            body: JSON.stringify({ email, password }),
        });
        if (data.token) {
            setToken(data.token);
            setDoctor(data.doctor);
        }
        return data;
    }

    async function register(fields) {
        const data = await request('/auth/register', {
            method: 'POST',
            body: JSON.stringify(fields),
        });
        if (data.token) {
            setToken(data.token);
            setDoctor(data.doctor);
        }
        return data;
    }

    // ── Drugs ──
    async function searchDrugs(query) {
        return request(`/drugs/?q=${encodeURIComponent(query)}`);
    }

    async function getDrug(id) {
        return request(`/drugs/${id}`);
    }

    async function getDrugByName(name) {
        return request(`/drugs/by-name/${encodeURIComponent(name)}`);
    }

    // ── Chat ──
    async function chat(query, conversationHistory) {
        const payload = { query };
        if (conversationHistory && conversationHistory.length) {
            payload.conversation_history = conversationHistory;
        }
        return request('/chat/', {
            method: 'POST',
            body: JSON.stringify(payload),
        });
    }

    // ── Comparison ──
    async function compareDrugs(drugNames) {
        return request('/comparison/', {
            method: 'POST',
            body: JSON.stringify({ drug_names: drugNames }),
        });
    }

    // ── Safety ──
    async function checkSafety(drugNames, context = {}) {
        return request('/safety/check', {
            method: 'POST',
            body: JSON.stringify({ drug_names: drugNames, context }),
        });
    }

    // ── Pricing ──
    async function getPricing(drugName) {
        return request(`/pricing/${encodeURIComponent(drugName)}`);
    }

    return {
        getToken, setToken, clearToken,
        getDoctor, setDoctor,
        login, register,
        searchDrugs, getDrug, getDrugByName,
        chat, compareDrugs, checkSafety, getPricing,
    };
})();
