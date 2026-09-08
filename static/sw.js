const CACHE_NAME = 'foodsaver-v1';
const urlsToCache = [
    '/',
    '/static/style.css',
    '/static/app.js'
];

self.addEventListener('install', event => {
    event.waitUntil(
        caches.open(CACHE_NAME)
            .then(cache => cache.addAll(urlsToCache))
    );
    self.skipWaiting();
});

self.addEventListener('activate', event => {
    event.waitUntil(
        caches.keys().then(cacheNames => {
            return Promise.all(
                cacheNames.map(cache => {
                    if (cache !== CACHE_NAME) {
                        return caches.delete(cache);
                    }
                })
            );
        })
    );
    self.clients.claim();
});

self.addEventListener('fetch', event => {
    event.respondWith(
        caches.match(event.request)
            .then(response => {
                if (response) {
                    return response;
                }
                return fetch(event.request);
            })
    );
});

self.addEventListener('push', event => {
    const data = event.data ? event.data.json() : {};
    
    const title = data.title || 'FoodSaver Alert';
    const options = {
        body: data.body || 'You have items expiring soon!',
        icon: data.icon || '/static/favicon.ico',
        badge: data.badge || '/static/favicon.ico',
        vibrate: [200, 100, 200],
        tag: data.tag || 'food-expiry',
        renotify: true,
        requireInteraction: true,
        actions: [
            { action: 'open', title: 'Open App', icon: '/static/favicon.ico' },
            { action: 'dismiss', title: 'Dismiss', icon: '/static/favicon.ico' }
        ],
        data: {
            url: data.url || '/',
            items: data.items || []
        }
    };

    event.waitUntil(
        self.registration.showNotification(title, options)
    );
});

self.addEventListener('notificationclick', event => {
    event.notification.close();

    if (event.action === 'dismiss') {
        return;
    }

    const urlToOpen = event.notification.data.url || '/';

    event.waitUntil(
        clients.matchAll({ type: 'window', includeUncontrolled: true })
            .then(clientList => {
                for (const client of clientList) {
                    if (client.url.includes(self.location.origin) && 'focus' in client) {
                        client.focus();
                        client.navigate(urlToOpen);
                        return;
                    }
                }
                return clients.openWindow(urlToOpen);
            })
    );
});

self.addEventListener('message', event => {
    if (event.data && event.data.type === 'CHECK_EXPIRY') {
        const items = event.data.items || [];
        if (items.length > 0) {
            const expiredItems = items.filter(i => i.days_left < 0);
            const urgentItems = items.filter(i => i.days_left >= 0 && i.days_left <= 1);
            const warningItems = items.filter(i => i.days_left > 1 && i.days_left <= 3);

            let body = '';
            if (expiredItems.length > 0) {
                body += `${expiredItems.length} item(s) EXPIRED: ${expiredItems.map(i => i.name).join(', ')}. `;
            }
            if (urgentItems.length > 0) {
                body += `${urgentItems.length} item(s) expiring TODAY/TOMORROW: ${urgentItems.map(i => i.name).join(', ')}. `;
            }
            if (warningItems.length > 0) {
                body += `${warningItems.length} item(s) expiring in 3 days: ${warningItems.map(i => i.name).join(', ')}. `;
            }

            if (body) {
                self.registration.showNotification('FoodSaver - Items Expiring Soon!', {
                    body: body.trim(),
                    icon: '/static/favicon.ico',
                    badge: '/static/favicon.ico',
                    vibrate: [200, 100, 200, 100, 200],
                    tag: 'food-expiry-batch',
                    renotify: true,
                    requireInteraction: true,
                    actions: [
                        { action: 'open', title: 'View Items' },
                        { action: 'dismiss', title: 'Dismiss' }
                    ],
                    data: { url: '/items' }
                });
            }
        }
    }
});
