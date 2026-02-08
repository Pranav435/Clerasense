/**
 * Clerasense – Application Shell Controller
 * Manages routing between modules, authentication state, and global search.
 */

const App = (() => {
    let currentModule = 'druginfo';
    let _userCountry = '';          // detected ISO country code
    let _userCountryName = '';      // human-readable name

    const modules = {
        druginfo: DrugInfoModule,
        askmore: AskMoreModule,
        comparison: ComparisonModule,
        prescription: PrescriptionVerifierModule,
    };

    /* ── Country detection via IP geolocation ── */
    async function detectCountry() {
        // Check cache first
        const cached = localStorage.getItem('clerasense_country');
        const cachedName = localStorage.getItem('clerasense_country_name');
        if (cached) {
            _userCountry = cached;
            _userCountryName = cachedName || cached;
            return;
        }
        try {
            const resp = await fetch('https://ipapi.co/json/', { timeout: 5000 });
            if (resp.ok) {
                const data = await resp.json();
                _userCountry = (data.country_code || 'US').toUpperCase();
                _userCountryName = data.country_name || _userCountry;
                localStorage.setItem('clerasense_country', _userCountry);
                localStorage.setItem('clerasense_country_name', _userCountryName);
            }
        } catch (e) {
            console.warn('Country detection failed, defaulting to US');
            _userCountry = 'US';
            _userCountryName = 'United States';
        }
    }

    function getUserCountry() { return _userCountry || 'US'; }
    function getUserCountryName() { return _userCountryName || 'United States'; }

    function init() {
        Auth.init();

        // Detect user's country in background (non-blocking)
        detectCountry();

        // Check for existing session
        const token = API.getToken();
        if (token) {
            showApp();
        } else {
            showAuth();
        }
    }

    function showAuth() {
        document.getElementById('auth-screen').classList.remove('hidden');
        document.getElementById('app-shell').classList.add('hidden');
    }

    function showApp() {
        document.getElementById('auth-screen').classList.add('hidden');
        document.getElementById('app-shell').classList.remove('hidden');

        // Set user name
        const doctor = API.getDoctor();
        if (doctor) {
            document.getElementById('user-name').textContent = doctor.full_name;
        }

        // Initialize navigation
        setupNavigation();
        setupGlobalSearch();
        setupLogout();

        // Render default module
        renderModule(currentModule);
    }

    function setupNavigation() {
        const buttons = document.querySelectorAll('.sidebar-btn');
        buttons.forEach(btn => {
            btn.addEventListener('click', () => {
                buttons.forEach(b => b.classList.remove('active'));
                btn.classList.add('active');
                const moduleName = btn.dataset.module;
                renderModule(moduleName);
            });
        });
    }

    function setupGlobalSearch() {
        const input = document.getElementById('global-search');
        const btn = document.getElementById('global-search-btn');

        async function doSearch() {
            const q = input.value.trim();
            if (!q) return;

            // Switch to Drug Information and fill the search
            currentModule = 'druginfo';
            document.querySelectorAll('.sidebar-btn').forEach(b => {
                b.classList.toggle('active', b.dataset.module === 'druginfo');
            });
            renderModule('druginfo');

            // Fill the drug-info search input and trigger lookup
            setTimeout(() => {
                const drugInput = document.getElementById('druginfo-input');
                if (drugInput) {
                    drugInput.value = q;
                    document.getElementById('druginfo-search-btn').click();
                    input.value = '';
                }
            }, 100);
        }

        btn.addEventListener('click', doSearch);
        input.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') doSearch();
        });
    }

    function setupLogout() {
        document.getElementById('logout-btn').addEventListener('click', Auth.logout);
    }

    function renderModule(name) {
        currentModule = name;
        const container = document.getElementById('content-area');
        const mod = modules[name];
        if (mod) {
            mod.render(container);
        } else {
            container.innerHTML = '<div class="empty-state"><h3>Module not found</h3></div>';
        }
    }

    // Auto-init on DOM ready
    document.addEventListener('DOMContentLoaded', init);

    return { showApp, showAuth, getUserCountry, getUserCountryName };
})();
