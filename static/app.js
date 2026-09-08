document.addEventListener('DOMContentLoaded', function() {
    const toastContainer = document.createElement('div');
    toastContainer.className = 'toast-container';
    document.body.appendChild(toastContainer);

    createParticles();

    function showToast(message, type = 'success') {
        const toast = document.createElement('div');
        toast.className = `toast toast-${type}`;
        const icons = { success: 'check-circle', warning: 'exclamation-triangle', info: 'info-circle', error: 'times-circle' };
        toast.innerHTML = `<i class="fas fa-${icons[type] || 'info-circle'}"></i><span>${message}</span>`;
        toastContainer.appendChild(toast);
        setTimeout(() => {
            toast.style.animation = 'toastSlide 0.4s ease reverse';
            setTimeout(() => toast.remove(), 400);
        }, 4000);
    }
    window.showToast = showToast;

    function createParticles() {
        const container = document.createElement('div');
        container.className = 'particles';
        document.body.appendChild(container);
        const colors = ['#6366f1', '#8b5cf6', '#ec4899', '#06b6d4', '#10b981'];
        for (let i = 0; i < 15; i++) {
            const p = document.createElement('div');
            p.className = 'particle';
            p.style.left = Math.random() * 100 + '%';
            p.style.animationDelay = Math.random() * 15 + 's';
            p.style.animationDuration = (15 + Math.random() * 10) + 's';
            p.style.background = colors[Math.floor(Math.random() * colors.length)];
            p.style.width = (3 + Math.random() * 5) + 'px';
            p.style.height = p.style.width;
            container.appendChild(p);
        }
    }

    document.querySelectorAll('.alert').forEach(alert => {
        setTimeout(() => {
            alert.style.animation = 'slideDown 0.4s ease reverse';
            setTimeout(() => alert.remove(), 400);
        }, 5000);
    });

    const scoreEl = document.querySelector('.score-value');
    if (scoreEl) {
        const target = parseInt(scoreEl.textContent);
        if (!isNaN(target)) {
            let current = 0;
            const increment = target / 40;
            const timer = setInterval(() => {
                current += increment;
                if (current >= target) { current = target; clearInterval(timer); }
                scoreEl.textContent = Math.round(current);
            }, 25);
        }
    }

    document.querySelectorAll('.shelf-bar div').forEach(bar => {
        const width = bar.style.width;
        bar.style.width = '0';
        setTimeout(() => { bar.style.width = width; }, 200);
    });

    document.querySelectorAll('.reason-bar .bar div').forEach(bar => {
        const width = bar.style.width;
        bar.style.width = '0';
        setTimeout(() => { bar.style.width = width; }, 300);
    });

    document.querySelectorAll('.stat-card').forEach((card, index) => {
        card.style.animationDelay = (index * 0.1) + 's';
    });

    const categorySelect = document.getElementById('category');
    const purchaseDate = document.getElementById('purchase_date');
    const expiryDate = document.getElementById('expiry_date');
    if (categorySelect && purchaseDate && expiryDate) {
        function updateExpiry() {
            const option = categorySelect.options[categorySelect.selectedIndex];
            const match = option.text.match(/\((\d+) days/);
            if (match && purchaseDate.value) {
                const shelfLife = parseInt(match[1]);
                const purchase = new Date(purchaseDate.value);
                purchase.setDate(purchase.getDate() + shelfLife);
                expiryDate.value = purchase.toISOString().split('T')[0];
            }
        }
        categorySelect.addEventListener('change', updateExpiry);
        purchaseDate.addEventListener('change', updateExpiry);
        if (purchaseDate.value) updateExpiry();
    }

    document.querySelectorAll('form').forEach(form => {
        form.addEventListener('submit', function() {
            const submitBtn = this.querySelector('button[type="submit"]');
            if (submitBtn && !submitBtn.classList.contains('btn-delete')) {
                submitBtn.disabled = true;
                submitBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Processing...';
            }
        });
    });

    // ==================== ITEM ACTIONS ====================
    
    window.markConsumed = function(itemId) {
        const form = document.createElement('form');
        form.method = 'POST';
        form.action = '/consume/' + itemId;
        document.body.appendChild(form);
        form.submit();
    };

    window.markWasted = function(itemId) {
        const form = document.createElement('form');
        form.method = 'POST';
        form.action = '/waste/' + itemId;
        const reasonInput = document.createElement('input');
        reasonInput.type = 'hidden';
        reasonInput.name = 'reason';
        reasonInput.value = 'expired';
        form.appendChild(reasonInput);
        document.body.appendChild(form);
        form.submit();
    };

    window.markPurchased = function(itemId) {
        const form = document.createElement('form');
        form.method = 'POST';
        form.action = '/shopping/purchase/' + itemId;
        document.body.appendChild(form);
        form.submit();
    };

    // ==================== NOTIFICATIONS ====================
    
    const notifToggle = document.getElementById('notificationToggle');

    if (notifToggle) {
        let notifEnabled = localStorage.getItem('notifications_enabled') === 'true';
        updateNotifUI();

        notifToggle.addEventListener('click', function() {
            if (!('Notification' in window)) {
                showToast('Your browser does not support notifications.', 'error');
                return;
            }

            if (notifEnabled) {
                notifEnabled = false;
                localStorage.setItem('notifications_enabled', 'false');
                updateNotifUI();
                showToast('Notifications disabled.', 'info');
            } else {
                Notification.requestPermission().then(function(permission) {
                    if (permission === 'granted') {
                        notifEnabled = true;
                        localStorage.setItem('notifications_enabled', 'true');
                        updateNotifUI();
                        showToast('Notifications enabled! You will be alerted about expiring items.', 'success');
                        checkExpiringItems(true);
                    } else {
                        showToast('Please allow notifications in your browser settings.', 'warning');
                    }
                });
            }
        });

        function updateNotifUI() {
            if (notifEnabled) {
                notifToggle.innerHTML = '<i class="fas fa-bell-slash"></i> Disable Notifications';
                notifToggle.className = 'btn btn-outline';
            } else {
                notifToggle.innerHTML = '<i class="fas fa-bell"></i> Enable Notifications';
                notifToggle.className = 'btn btn-primary';
            }
        }

        function sendNotification(title, body, url) {
            if (!notifEnabled) return;
            if ('Notification' in window && Notification.permission === 'granted') {
                const n = new Notification(title, {
                    body: body,
                    icon: '/static/favicon.ico',
                    tag: 'food-expiry-' + Date.now(),
                    requireInteraction: true
                });
                n.onclick = function() {
                    window.focus();
                    if (url) window.location.href = url;
                    n.close();
                };
            }
        }

        let lastExpiringCount = 0;

        function checkExpiringItems(notify) {
            fetch('/api/expiring?days=3')
                .then(function(response) { return response.json(); })
                .then(function(items) {
                    const today = new Date().toISOString().split('T')[0];
                    const expired = items.filter(function(i) { return i.expiry_date < today; });
                    const urgent = items.filter(function(i) {
                        var diff = (new Date(i.expiry_date) - new Date(today)) / (1000*60*60*24);
                        return diff >= 0 && diff <= 1;
                    });
                    const warning = items.filter(function(i) {
                        var diff = (new Date(i.expiry_date) - new Date(today)) / (1000*60*60*24);
                        return diff > 1 && diff <= 3;
                    });

                    if (notify && items.length > 0) {
                        var body = '';
                        if (expired.length > 0) body += expired.length + ' item(s) EXPIRED. ';
                        if (urgent.length > 0) body += urgent.length + ' item(s) expiring TODAY/TOMORROW. ';
                        if (warning.length > 0) body += warning.length + ' item(s) expiring in 3 days. ';
                        if (body) sendNotification('FoodSaver - Items Expiring Soon!', body.trim(), '/items');
                    } else if (notify && items.length === 0) {
                        sendNotification('FoodSaver', 'All your food items are fresh! Great job!', '/');
                    }

                    if (items.length > lastExpiringCount && lastExpiringCount > 0 && !notify) {
                        showToast('Warning: ' + (items.length - lastExpiringCount) + ' new item(s) expiring soon!', 'warning');
                    }
                    lastExpiringCount = items.length;

                    var badge = document.querySelector('.alert-badge');
                    if (badge && items.length > 0) {
                        badge.innerHTML = '<i class="fas fa-exclamation-triangle"></i> ' + items.length + ' items expiring soon';
                    }
                })
                .catch(function(err) { console.log('Polling error:', err); });
        }

        setInterval(function() { checkExpiringItems(false); }, 30000);
        if (notifEnabled) checkExpiringItems(true);
    }

    // Intersection Observer
    var observer = new IntersectionObserver(function(entries) {
        entries.forEach(function(entry) {
            if (entry.isIntersecting) {
                entry.target.style.opacity = '1';
                entry.target.style.transform = 'translateY(0)';
            }
        });
    }, { threshold: 0.1, rootMargin: '0px 0px -50px 0px' });

    document.querySelectorAll('.card, .stat-card').forEach(function(el) {
        el.style.opacity = '0';
        el.style.transform = 'translateY(30px)';
        el.style.transition = 'all 0.6s ease';
        observer.observe(el);
    });
});
