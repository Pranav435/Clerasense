/**
 * Clerasense – Shared Currency Utilities
 * Auto-detects user location, fetches exchange rates, and provides
 * conversion + formatting helpers used across modules.
 */

const Currency = (() => {

    let _currency = 'USD';
    let _rates = null;
    let _locationNote = '';
    let _ready = false;

    const SYMBOLS = {
        USD: '$', EUR: '€', GBP: '£', INR: '₹', JPY: '¥', CNY: '¥',
        AUD: 'A$', CAD: 'C$', CHF: 'CHF', KRW: '₩', BRL: 'R$',
        MXN: 'MX$', ZAR: 'R', SGD: 'S$', HKD: 'HK$', SEK: 'kr',
        NOK: 'kr', DKK: 'kr', NZD: 'NZ$', THB: '฿', MYR: 'RM',
        PHP: '₱', IDR: 'Rp', AED: 'AED', SAR: 'SAR', BDT: '৳',
        PKR: 'Rs', LKR: 'Rs', NPR: 'Rs', EGP: 'E£', NGN: '₦',
    };

    const COUNTRY_MAP = {
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

    /** Detect currency from IP geolocation. */
    async function _detectCurrency() {
        try {
            const res = await fetch('https://ipapi.co/json/', { signal: AbortSignal.timeout(4000) });
            if (!res.ok) return;
            const geo = await res.json();
            const cc = (geo.country_code || '').toUpperCase();
            const country = geo.country_name || cc;
            const mapped = COUNTRY_MAP[cc];
            if (mapped && mapped !== 'USD') {
                _currency = mapped;
                _locationNote = `Showing prices in ${mapped} based on your approximate location (${country}). No precise location is accessed.`;
            }
        } catch { /* fallback to USD */ }
    }

    /** Fetch exchange rates (USD base). Cached for session. */
    async function loadRates() {
        if (_rates) return;
        try {
            const res = await fetch('https://open.er-api.com/v6/latest/USD', { signal: AbortSignal.timeout(5000) });
            if (!res.ok) return;
            const data = await res.json();
            if (data.rates) _rates = data.rates;
        } catch { /* stays null → show USD */ }
    }

    /** Convert a USD amount to the active currency. */
    function convert(usd) {
        if (!usd || !_rates || _currency === 'USD') return usd;
        const rate = _rates[_currency];
        return rate ? usd * rate : usd;
    }

    /** Format a USD amount in the active currency with symbol. */
    function format(usd, decimals = 2) {
        const sym = SYMBOLS[_currency] || _currency + ' ';
        const val = convert(usd);
        if (val === null || val === undefined) return 'N/A';
        return `${sym}${val.toFixed(decimals)}`;
    }

    /** Current active currency code. */
    function current() { return _currency; }

    /** Set active currency code. */
    function setCurrency(code) { _currency = code; }

    /** Location note string. */
    function locationNote() { return _locationNote; }

    /** Build <option> list for a <select>. */
    function optionsHtml() {
        return Object.keys(SYMBOLS).map(c =>
            `<option value="${c}" ${c === _currency ? 'selected' : ''}>${c} (${SYMBOLS[c]})</option>`
        ).join('');
    }

    // Auto-init on load
    const _initPromise = (async () => {
        await _detectCurrency();
        await loadRates();
        _ready = true;
    })();

    /** Wait until detection + rates are loaded. */
    function ready() { return _initPromise; }

    return { loadRates, convert, format, current, setCurrency, locationNote, optionsHtml, ready, SYMBOLS };
})();
