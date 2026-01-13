document.addEventListener('DOMContentLoaded', function () {

    // 1. Password Visibility Toggle (Global)
    const toggleButtons = document.querySelectorAll('.toggle-password');
    toggleButtons.forEach(button => {
        button.addEventListener('click', function () {
            const input = this.previousElementSibling;
            if (input.type === 'password') {
                input.type = 'text';
                this.innerHTML = '<i class="fas fa-eye-slash"></i>';
            } else {
                input.type = 'password';
                this.innerHTML = '<i class="fas fa-eye"></i>';
            }
        });
    });

    // 2. Initialize Tooltips (Bootstrap 5)
    var tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'))
    var tooltipList = tooltipTriggerList.map(function (tooltipTriggerEl) {
        return new bootstrap.Tooltip(tooltipTriggerEl)
    });

    // 3. Confirm Delete Actions
    const deleteButtons = document.querySelectorAll('.btn-danger');
    deleteButtons.forEach(btn => {
        btn.addEventListener('click', function (e) {
            if (this.dataset.confirm) {
                if (!confirm(this.dataset.confirm)) {
                    e.preventDefault();
                }
            }
        });
    });
});

// Helper: Format Date logic if needed on client side
function formatDate(dateString) {
    const options = { year: 'numeric', month: 'short', day: 'numeric' };
    return new Date(dateString).toLocaleDateString(undefined, options);
}

// Helper: Show Toast Notification (Needs Bootstrap Toast HTML in layout)
function showToast(message, type = 'info') {
    // Implementation for dynamic toast messages
    console.log(`[${type}] ${message}`);
}