
(function () {
    const el = document.getElementById('total-subjects');
    if (!el) return;

    // endpoint (served by admin blueprint, adjust endpoint path if different)
    const url = "/admin/subject_count"; // Hardcoding for now, as url_for is not available in JS files

    async function refreshCount() {
        try {
            const res = await fetch(url, {cache: "no-store"});
            if (!res.ok) throw new Error('Network error');
            const data = await res.json();
            if (typeof data.count === 'number') {
                el.textContent = data.count;
            }
        } catch (err) {
            // silent fail; keep existing number
            console.error('Failed to refresh subject count', err);
        }
    }

    // poll every 5 seconds (adjust as needed)
    setInterval(refreshCount, 5000);
    // initial load after page paint
    window.addEventListener('load', refreshCount);
})();
