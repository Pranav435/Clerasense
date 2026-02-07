/**
 * Clerasense – Auth Module
 * Handles login, registration, and session management.
 */

const Auth = (() => {
    function init() {
        const loginForm = document.getElementById('login-form');
        const registerForm = document.getElementById('register-form');
        const showRegister = document.getElementById('show-register');
        const showLogin = document.getElementById('show-login');

        showRegister.addEventListener('click', (e) => {
            e.preventDefault();
            loginForm.classList.add('hidden');
            registerForm.classList.remove('hidden');
        });

        showLogin.addEventListener('click', (e) => {
            e.preventDefault();
            registerForm.classList.add('hidden');
            loginForm.classList.remove('hidden');
        });

        loginForm.addEventListener('submit', handleLogin);
        registerForm.addEventListener('submit', handleRegister);
    }

    async function handleLogin(e) {
        e.preventDefault();
        const errEl = document.getElementById('login-error');
        errEl.classList.add('hidden');

        const email = document.getElementById('login-email').value.trim();
        const password = document.getElementById('login-password').value;

        if (!email || !password) {
            showError(errEl, 'Please fill in all fields.');
            return;
        }

        const data = await API.login(email, password);
        if (data.error) {
            showError(errEl, data.error);
        } else {
            App.showApp();
        }
    }

    async function handleRegister(e) {
        e.preventDefault();
        const errEl = document.getElementById('register-error');
        errEl.classList.add('hidden');

        const fields = {
            full_name: document.getElementById('reg-name').value.trim(),
            email: document.getElementById('reg-email').value.trim(),
            license_number: document.getElementById('reg-license').value.trim(),
            specialization: document.getElementById('reg-specialization').value.trim(),
            password: document.getElementById('reg-password').value,
        };

        if (!fields.full_name || !fields.email || !fields.license_number || !fields.password) {
            showError(errEl, 'Please fill in all required fields.');
            return;
        }

        const data = await API.register(fields);
        if (data.error) {
            showError(errEl, data.error);
        } else {
            App.showApp();
        }
    }

    function logout() {
        API.clearToken();
        window.location.reload();
    }

    function showError(el, msg) {
        el.textContent = msg;
        el.classList.remove('hidden');
    }

    return { init, logout };
})();
