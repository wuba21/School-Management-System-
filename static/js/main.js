/**
 * Smart School Management and Academic Information System (SSMS)
 * Main Client-side Script
 */

document.addEventListener('DOMContentLoaded', function () {
    console.log('SSMS: Smart School Management System initialized.');

    // Auto-dismiss Django alert messages after 5 seconds
    const alerts = document.querySelectorAll('.alert-dismissible');
    alerts.forEach(function (alert) {
        setTimeout(function () {
            const bsAlert = new bootstrap.Alert(alert);
            bsAlert.close();
        }, 5000);
    });
});
