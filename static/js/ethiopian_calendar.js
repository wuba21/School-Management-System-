/**
 * Ethiopian Calendar (ዓውደ አውራኅ) Client-Side Engine & Interactive Date Picker Widget
 * Smart School Management and Academic Information System (SSMS)
 * 100% Offline, Pure Vanilla JavaScript, Exact JDN algorithms.
 */

(function () {
    'use strict';

    // -------------------------------------------------------------------------
    // 1. CONSTANTS & METADATA
    // -------------------------------------------------------------------------
    const ETH_MONTHS_EN = [
        '', 'Meskerem', 'Tikimt', 'Hidar', 'Tahsas', 'Tir', 'Yekatit',
        'Megabit', 'Miazia', 'Ginbot', 'Sene', 'Hamle', 'Nehase', 'Pagume'
    ];

    const ETH_MONTHS_AM = [
        '', 'መስከረም', 'ጥቅምት', 'ኅዳር', 'ታኅሣሥ', 'ጥር', 'የካቲት',
        'መጋቢት', 'ሚያዝያ', 'ግንቦት', 'ሰኔ', 'ሐምሌ', 'ነሐሴ', 'ጳጉሜ'
    ];

    // -------------------------------------------------------------------------
    // 2. MATHEMATICAL CONVERSIONS (JDN)
    // -------------------------------------------------------------------------
    function gregorianToJdn(year, month, day) {
        const a = Math.floor((14 - month) / 12);
        const y = year + 4800 - a;
        const m = month + 12 * a - 3;
        return day + Math.floor((153 * m + 2) / 5) + 365 * y + Math.floor(y / 4) - Math.floor(y / 100) + Math.floor(y / 400) - 32045;
    }

    function jdnToGregorian(jdn) {
        const a = jdn + 32044;
        const b = Math.floor((4 * a + 3) / 146097);
        const c = a - Math.floor((146097 * b) / 4);
        const d = Math.floor((4 * c + 3) / 1461);
        const e = c - Math.floor((1461 * d) / 4);
        const m = Math.floor((5 * e + 2) / 153);
        const day = e - Math.floor((153 * m + 2) / 5) + 1;
        const month = m + 3 - 12 * Math.floor(m / 10);
        const year = 100 * b + d - 4800 + Math.floor(m / 10);
        return { year, month, day };
    }

    function jdnToEthiopian(jdn) {
        const r = (jdn - 1723856) % 1461;
        const n = (r % 365) + 365 * Math.floor(r / 1460);
        const year = 4 * Math.floor((jdn - 1723856) / 1461) + Math.floor(r / 365) - Math.floor(r / 1460);
        const month = Math.floor(n / 30) + 1;
        const day = (n % 30) + 1;
        return {
            year,
            month,
            day,
            monthNameEn: ETH_MONTHS_EN[month] || '',
            monthNameAm: ETH_MONTHS_AM[month] || '',
            isLeapYear: (year % 4 === 3)
        };
    }

    function ethiopianToJdn(year, month, day) {
        return (1723856 + 365) + 365 * (year - 1) + Math.floor(year / 4) + 30 * (month - 1) + day - 1;
    }

    function isEthiopianLeapYear(year) {
        return (year % 4 === 3);
    }

    function getEthiopianMonthDays(year, month) {
        if (month >= 1 && month <= 12) return 30;
        if (month === 13) return isEthiopianLeapYear(year) ? 6 : 5;
        return 30;
    }

    function gregorianToEthiopian(year, month, day) {
        const jdn = gregorianToJdn(year, month, day);
        return jdnToEthiopian(jdn);
    }

    function ethiopianToGregorian(year, month, day) {
        const jdn = ethiopianToJdn(year, month, day);
        const g = jdnToGregorian(jdn);
        const pad = (n) => String(n).padStart(2, '0');
        return {
            year: g.year,
            month: g.month,
            day: g.day,
            dateStr: `${g.year}-${pad(g.month)}-${pad(g.day)}`
        };
    }

    // Expose public API
    window.EthiopianCalendar = {
        gregorianToEthiopian,
        ethiopianToGregorian,
        isEthiopianLeapYear,
        getEthiopianMonthDays,
        ETH_MONTHS_EN,
        ETH_MONTHS_AM
    };

    // -------------------------------------------------------------------------
    // 3. AUTOMATIC DATE INPUT ENHANCER WIDGET
    // -------------------------------------------------------------------------
    function initDateInputEnhancers() {
        // Find all standard date inputs across forms (e.g. student DOB, admission date, attendance date)
        const dateInputs = document.querySelectorAll('input[type="date"]');

        dateInputs.forEach(input => {
            if (input.dataset.ethiopianEnhanced) return;
            input.dataset.ethiopianEnhanced = 'true';

            // Create container for indicator pill and picker toggle button
            const wrapper = document.createElement('div');
            wrapper.className = 'ethiopian-date-pill mt-1 d-flex flex-wrap align-items-center justify-content-between gap-2 p-1 px-2 rounded bg-light border';
            wrapper.style.fontSize = '0.75rem';

            const indicator = document.createElement('span');
            indicator.className = 'text-primary fw-semibold';
            indicator.innerHTML = '<i class="bi bi-calendar-event me-1"></i> <span class="eth-date-text">Ethiopian Date</span>';

            const toggleBtn = document.createElement('button');
            toggleBtn.type = 'button';
            toggleBtn.className = 'btn btn-outline-primary btn-xs py-0 px-2';
            toggleBtn.style.fontSize = '0.7rem';
            toggleBtn.innerHTML = '<i class="bi bi-pencil-square me-1"></i> Pick Ethiopian Date';

            wrapper.appendChild(indicator);
            wrapper.appendChild(toggleBtn);
            input.parentNode.insertBefore(wrapper, input.nextSibling);

            // Update function
            function updateIndicator() {
                if (!input.value) {
                    indicator.querySelector('.eth-date-text').textContent = 'Select date above or use picker';
                    return;
                }
                const parts = input.value.split('-');
                if (parts.length === 3) {
                    const gy = parseInt(parts[0], 10);
                    const gm = parseInt(parts[1], 10);
                    const gd = parseInt(parts[2], 10);
                    if (!isNaN(gy) && !isNaN(gm) && !isNaN(gd)) {
                        const eth = gregorianToEthiopian(gy, gm, gd);
                        indicator.querySelector('.eth-date-text').innerHTML =
                            `<strong>${eth.monthNameEn} ${eth.day}, ${eth.year} E.C.</strong> (${eth.monthNameAm} ${eth.day} ቀን ${eth.year} ዓ.ም.)`;
                    }
                }
            }

            input.addEventListener('change', updateIndicator);
            input.addEventListener('input', updateIndicator);
            updateIndicator();

            // Toggle Ethiopian Date Picker Modal / Popover
            toggleBtn.addEventListener('click', function () {
                openEthiopianDatePicker(input, updateIndicator);
            });
        });
    }

    // -------------------------------------------------------------------------
    // 4. ETHIOPIAN DATE PICKER MODAL
    // -------------------------------------------------------------------------
    function openEthiopianDatePicker(targetInput, onDateSelected) {
        let modalEl = document.getElementById('ssmsEthiopianDatePickerModal');
        if (!modalEl) {
            modalEl = document.createElement('div');
            modalEl.id = 'ssmsEthiopianDatePickerModal';
            modalEl.className = 'modal fade';
            modalEl.tabIndex = -1;
            modalEl.innerHTML = `
                <div class="modal-dialog modal-dialog-centered modal-sm">
                    <div class="modal-content shadow border-0">
                        <div class="modal-header bg-primary text-white py-2">
                            <h6 class="modal-title fw-bold">
                                <i class="bi bi-calendar3 me-2"></i>Ethiopian Date Picker (ዓውደ አውራኅ)
                            </h6>
                            <button type="button" class="btn-close btn-close-white" data-bs-dismiss="modal" aria-label="Close"></button>
                        </div>
                        <div class="modal-body p-3">
                            <div class="mb-2">
                                <label class="form-label small fw-semibold text-muted mb-1">Ethiopian Year (ዓመተ ምሕረት)</label>
                                <input type="number" id="ethModalYear" class="form-control form-control-sm font-monospace" min="1900" max="2100" value="2016">
                            </div>
                            <div class="mb-2">
                                <label class="form-label small fw-semibold text-muted mb-1">Ethiopian Month (ወር)</label>
                                <select id="ethModalMonth" class="form-select form-select-sm">
                                    <option value="1">1. Meskerem (መስከረም)</option>
                                    <option value="2">2. Tikimt (ጥቅምት)</option>
                                    <option value="3">3. Hidar (ኅዳር)</option>
                                    <option value="4">4. Tahsas (ታኅሣሥ)</option>
                                    <option value="5">5. Tir (ጥር)</option>
                                    <option value="6">6. Yekatit (የካቲት)</option>
                                    <option value="7">7. Megabit (መጋቢት)</option>
                                    <option value="8">8. Miazia (ሚያዝያ)</option>
                                    <option value="9">9. Ginbot (ግንቦት)</option>
                                    <option value="10">10. Sene (ሰኔ)</option>
                                    <option value="11">11. Hamle (ሐምሌ)</option>
                                    <option value="12">12. Nehase (ነሐሴ)</option>
                                    <option value="13">13. Pagume (ጳጉሜ - 5/6 days)</option>
                                </select>
                            </div>
                            <div class="mb-3">
                                <label class="form-label small fw-semibold text-muted mb-1">Day of Month (ቀን)</label>
                                <input type="number" id="ethModalDay" class="form-control form-control-sm font-monospace" min="1" max="30" value="1">
                                <div id="ethModalDayHelp" class="form-text text-xs text-muted">Months 1-12 have 30 days. Pagume has 5 or 6 days.</div>
                            </div>
                            <div class="alert alert-info py-2 small mb-0 font-monospace text-center">
                                <span class="text-muted">Gregorian Equivalent:</span><br>
                                <strong id="ethModalGregPreview">-</strong>
                            </div>
                        </div>
                        <div class="modal-footer py-2 bg-light">
                            <button type="button" class="btn btn-outline-secondary btn-sm" data-bs-dismiss="modal">Cancel</button>
                            <button type="button" id="ethModalApplyBtn" class="btn btn-primary btn-sm">
                                <i class="bi bi-check-lg me-1"></i> Apply Date
                            </button>
                        </div>
                    </div>
                </div>
            `;
            document.body.appendChild(modalEl);
        }

        const yearInput = document.getElementById('ethModalYear');
        const monthSelect = document.getElementById('ethModalMonth');
        const dayInput = document.getElementById('ethModalDay');
        const gregPreview = document.getElementById('ethModalGregPreview');
        const applyBtn = document.getElementById('ethModalApplyBtn');

        // Pre-fill from targetInput if it has a valid Gregorian date
        if (targetInput.value) {
            const p = targetInput.value.split('-');
            if (p.length === 3) {
                const eth = gregorianToEthiopian(parseInt(p[0], 10), parseInt(p[1], 10), parseInt(p[2], 10));
                yearInput.value = eth.year;
                monthSelect.value = eth.month;
                dayInput.value = eth.day;
            }
        } else {
            const todayEth = gregorianToEthiopian(new Date().getFullYear(), new Date().getMonth() + 1, new Date().getDate());
            yearInput.value = todayEth.year;
            monthSelect.value = todayEth.month;
            dayInput.value = todayEth.day;
        }

        function updatePreview() {
            const y = parseInt(yearInput.value, 10) || 2016;
            const m = parseInt(monthSelect.value, 10) || 1;
            let d = parseInt(dayInput.value, 10) || 1;

            const maxDays = getEthiopianMonthDays(y, m);
            dayInput.max = maxDays;
            if (d > maxDays) {
                d = maxDays;
                dayInput.value = d;
            }

            try {
                const g = ethiopianToGregorian(y, m, d);
                gregPreview.textContent = `${g.dateStr} (${ETH_MONTHS_EN[m]} ${d}, ${y} E.C.)`;
            } catch (err) {
                gregPreview.textContent = 'Invalid Ethiopian Date';
            }
        }

        yearInput.oninput = updatePreview;
        monthSelect.onchange = updatePreview;
        dayInput.oninput = updatePreview;
        updatePreview();

        const bsModal = new bootstrap.Modal(modalEl);
        bsModal.show();

        applyBtn.onclick = function () {
            const y = parseInt(yearInput.value, 10) || 2016;
            const m = parseInt(monthSelect.value, 10) || 1;
            const d = parseInt(dayInput.value, 10) || 1;
            const g = ethiopianToGregorian(y, m, d);
            targetInput.value = g.dateStr;
            targetInput.dispatchEvent(new Event('change', { bubbles: true }));
            if (typeof onDateSelected === 'function') onDateSelected();
            bsModal.hide();
        };
    }

    // -------------------------------------------------------------------------
    // 5. NAVBAR LIVE CALENDAR DISPLAY
    // -------------------------------------------------------------------------
    function initNavbarCalendar() {
        const navEl = document.querySelector('.ethiopian-navbar-date');
        if (navEl) {
            const today = new Date();
            const eth = gregorianToEthiopian(today.getFullYear(), today.getMonth() + 1, today.getDate());
            navEl.textContent = `${eth.monthNameEn} ${eth.day}, ${eth.year} E.C.`;
            navEl.title = `${eth.monthNameAm} ${eth.day} ቀን ${eth.year} ዓ.ም.`;
        }
    }

    // Initialize when DOM is ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', function () {
            initDateInputEnhancers();
            initNavbarCalendar();
        });
    } else {
        initDateInputEnhancers();
        initNavbarCalendar();
    }
})();
