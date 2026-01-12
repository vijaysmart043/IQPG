
document.addEventListener('DOMContentLoaded', function () {
    const buttons = document.querySelectorAll('.btn');

    buttons.forEach(button => {
        button.addEventListener('click', function (e) {
            // Create span element
            let ripple = document.createElement('span');
            ripple.classList.add('ripple');

            // Add it to the button
            this.appendChild(ripple);

            // Get position of X
            let x = e.clientX - e.target.offsetLeft;

            // Get position of Y
            let y = e.clientY - e.target.offsetTop;

            // Position the span element
            ripple.style.left = `${x}px`;
            ripple.style.top = `${y}px`;

            // Remove span after 0.3s
            setTimeout(() => {
                ripple.remove();
            }, 300);
        });
    });
});

// Add ripple CSS to the head
const style = document.createElement('style');
style.innerHTML = `
.ripple {
    position: absolute;
    background: rgba(255, 255, 255, 0.3);
    border-radius: 50%;
    transform: translate(-50%, -50%);
    animation: ripple-animation 0.6s linear;
    pointer-events: none;
}

@keyframes ripple-animation {
    0% {
        width: 0;
        height: 0;
        opacity: 0.5;
    }
    100% {
        width: 200px;
        height: 200px;
        opacity: 0;
    }
}
`;
document.head.appendChild(style);

// Bedim-style Navigation: menu toggle
const navMenu = document.getElementById('nav-menu')
const navToggle = document.getElementById('nav-toggle')
const navClose = document.getElementById('nav-close')

if (navToggle && navMenu) {
    navToggle.addEventListener('click', () => {
        navMenu.classList.add('show-menu')
    })
}

if (navClose && navMenu) {
    navClose.addEventListener('click', () => {
        navMenu.classList.remove('show-menu')
    })
}

// Hide loading on page load
window.addEventListener('load', () => {
    const loading = document.getElementById('loading');
    if (loading) {
        loading.style.display = 'none';
    }
})
