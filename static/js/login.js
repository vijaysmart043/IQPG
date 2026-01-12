
// Your web app's Firebase configuration
// For Firebase JS SDK v7.20.0 and later, measurementId is optional
const firebaseConfig = {
    apiKey: "AIzaSyDhLapj8eugpJcxAusvwIdwOlCnW5IEN88",
    authDomain: "authentication-c31f2.firebaseapp.com",
    projectId: "authentication-c31f2",
    storageBucket: "authentication-c31f2.firebasestorage.app",
    messagingSenderId: "557297790161",
    appId: "1:557297790161:web:47015d4bfebc7073ba29f0",
    measurementId: "G-5LDCJJFN94"
};

// Initialize Firebase
const app = firebase.initializeApp(firebaseConfig);
const analytics = firebase.analytics();
const auth = firebase.auth();

const loginForm = document.getElementById('login-form');
const emailInput = document.getElementById('email');
const passwordInput = document.getElementById('password');
const errorMessageDiv = document.getElementById('error-message');
const registerForm = document.getElementById('register-form');
const regFullNameInput = document.getElementById('reg-full-name');
const regDesignationInput = document.getElementById('reg-designation');
const regEmailInput = document.getElementById('reg-email');
const regPasswordInput = document.getElementById('reg-password');
const regConfirmPasswordInput = document.getElementById('reg-confirm-password');
const regFacultyIdInput = document.getElementById('reg-faculty-id-card');
const loginToggleBtn = document.getElementById('login-toggle');
const registerToggleBtn = document.getElementById('register-toggle');
const authForms = document.querySelectorAll('.auth-form');

if (loginForm) {
    loginForm.addEventListener('submit', (e) => {
        e.preventDefault();
        const email = emailInput.value;
        const password = passwordInput.value;

        errorMessageDiv.classList.add('d-none');

        auth.signInWithEmailAndPassword(email, password)
            .then((userCredential) => {
                return userCredential.user.getIdToken();
            })
            .then(idToken => {
                return fetch('/admin/login', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({ idToken: idToken })
                });
            })
            .then(response => {
                if (response.ok) {
                    window.location.href = '/admin/dashboard';
                } else {
                    return response.json().then(data => {
                        throw new Error(data.message || 'Server validation failed.');
                    });
                }
            })
            .catch((error) => {
                let errorMessage = 'Login failed. ';

                if (error.code) {
                    switch(error.code) {
                        case 'auth/invalid-email':
                            errorMessage = 'Invalid email address. Please check your email format.';
                            break;
                        case 'auth/user-disabled':
                            errorMessage = 'This account has been disabled. Please contact support.';
                            break;
                        case 'auth/user-not-found':
                            errorMessage = 'No account found with this email. Please register first or check your email.';
                            break;
                        case 'auth/wrong-password':
                            errorMessage = 'Incorrect password. Please try again or use "Register" to create an account.';
                            break;
                        case 'auth/invalid-credential':
                        case 'auth/invalid-login-credentials':
                            errorMessage = 'Invalid email or password. Please check your credentials or register a new account.';
                            break;
                        case 'auth/too-many-requests':
                            errorMessage = 'Too many failed login attempts. Please try again later.';
                            break;
                        case 'auth/network-request-failed':
                            errorMessage = 'Network error. Please check your internet connection.';
                            break;
                        default:
                            errorMessage = `Error: ${error.message || error.code || 'Unknown error occurred'}`;
                    }
                } else {
                    errorMessage = `Error: ${error.message || 'Unknown error occurred'}`;
                }

                errorMessageDiv.textContent = errorMessage;
                errorMessageDiv.classList.remove('d-none');
            });
    });
}

function setActiveForm(target) {
    authForms.forEach(form => {
        form.classList.remove('auth-form-active');
    });
    if (target === 'login' && loginForm) {
        loginForm.classList.add('auth-form-active');
    }
    if (target === 'register' && registerForm) {
        registerForm.classList.add('auth-form-active');
    }

    if (loginToggleBtn && registerToggleBtn) {
        if (target === 'login') {
            loginToggleBtn.classList.add('auth-toggle-active');
            registerToggleBtn.classList.remove('auth-toggle-active');
        } else {
            registerToggleBtn.classList.add('auth-toggle-active');
            loginToggleBtn.classList.remove('auth-toggle-active');
        }
    }
}

if (loginToggleBtn) {
    loginToggleBtn.addEventListener('click', () => setActiveForm('login'));
}

if (registerToggleBtn) {
    registerToggleBtn.addEventListener('click', () => setActiveForm('register'));
}

if (registerForm) {
    registerForm.addEventListener('submit', (e) => {
        e.preventDefault();

        const fullName = regFullNameInput.value.trim();
        const designation = regDesignationInput.value.trim();
        const email = regEmailInput.value.trim();
        const password = regPasswordInput.value;
        const confirmPassword = regConfirmPasswordInput.value;
        const facultyFile = regFacultyIdInput.files[0];

        if (!fullName || !designation || !email || !password || !confirmPassword) {
            errorMessageDiv.textContent = 'Please fill in all registration fields.';
            errorMessageDiv.classList.remove('d-none');
            return;
        }

        if (password !== confirmPassword) {
            errorMessageDiv.textContent = 'Password and confirm password do not match.';
            errorMessageDiv.classList.remove('d-none');
            return;
        }

        if (!facultyFile) {
            errorMessageDiv.textContent = 'Please upload your faculty ID card.';
            errorMessageDiv.classList.remove('d-none');
            return;
        }

        errorMessageDiv.classList.add('d-none');

        auth.createUserWithEmailAndPassword(email, password)
            .then((userCredential) => userCredential.user.getIdToken())
            .then((idToken) =>
                fetch('/admin/login', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ idToken })
                })
            )
            .then((response) => {
                if (!response.ok) {
                    return response.json().then((d) => {
                        throw new Error(d.message || 'Server validation failed during login.');
                    });
                }

                const formData = new FormData();
                formData.append('full_name', fullName);
                formData.append('designation', designation);
                formData.append('email', email);
                formData.append('faculty_id_card', facultyFile);

                return fetch('/admin/register', {
                    method: 'POST',
                    body: formData
                });
            })
            .then((response) => {
                if (!response.ok) {
                    return response.json().then((d) => {
                        throw new Error(d.message || 'Server validation failed during registration metadata save.');
                    });
                }
                window.location.href = '/admin/dashboard';
            })
            .catch((error) => {
                let errorMessage = 'Registration failed. ';

                if (error.code) {
                    switch (error.code) {
                        case 'auth/email-already-in-use':
                            errorMessage = 'This email is already registered. Please log in instead.';
                            break;
                        case 'auth/invalid-email':
                            errorMessage = 'Invalid email address. Please use a valid email format.';
                            break;
                        case 'auth/operation-not-allowed':
                            errorMessage = 'Email/password accounts are not enabled. Please contact support.';
                            break;
                        case 'auth/weak-password':
                            errorMessage = 'Password is too weak. Please use at least 6 characters.';
                            break;
                        case 'auth/network-request-failed':
                            errorMessage = 'Network error. Please check your internet connection.';
                            break;
                        default:
                            errorMessage = `Registration error: ${error.message || error.code || 'Unknown error'}`;
                    }
                } else {
                    errorMessage = `Registration error: ${error.message || 'Unknown error occurred'}`;
                }

                errorMessageDiv.textContent = errorMessage;
                errorMessageDiv.classList.remove('d-none');
            });
    });
}
// Form Wave Animation
const labels = document.querySelectorAll('.form-wave label')

labels.forEach(label => {
    label.innerHTML = label.innerText
        .split('')
        .map((letter, idx) => `<span style="transition-delay:${idx * 50}ms">${letter}</span>`)
        .join('')
})
