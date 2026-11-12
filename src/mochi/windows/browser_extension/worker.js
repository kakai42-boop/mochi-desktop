import {attemptClose} from './mood.mjs';

const HOST = 'com.mochidesktop.browser_mood';
const ALARM = 'mochi-mood-check';
const brands = navigator.userAgentData?.brands ?? [];
const edge = brands.some(({brand}) => brand === 'Microsoft Edge')
    || navigator.userAgent.includes('Edg/');
const browserBrand = edge ? 'edge' : 'chrome';
let revision = 0;
let checking = false;

const invalidate = () => { revision += 1; };
chrome.windows.onFocusChanged.addListener(invalidate);
chrome.windows.onBoundsChanged.addListener(invalidate);
chrome.tabs.onActivated.addListener(invalidate);
chrome.tabs.onRemoved.addListener(invalidate);
chrome.tabs.onDetached.addListener(invalidate);
chrome.tabs.onReplaced.addListener(invalidate);
chrome.tabs.onUpdated.addListener((_tabId, change, tab) => {
    if (tab.active && (change.status === 'loading' || change.pinned !== undefined)) invalidate();
});

async function send(message) {
    try {
        return await chrome.runtime.sendNativeMessage(HOST, message);
    } catch {
        return {};
    }
}

async function check() {
    if (checking) return;
    checking = true;
    try {
        await attemptClose({
            browser: chrome, brand: browserBrand, send,
            wait: milliseconds => new Promise(resolve => setTimeout(resolve, milliseconds)),
            revision: () => revision,
        });
    } catch {
        // A browser window or tab can disappear at any point.
    } finally {
        checking = false;
    }
}

async function ensureAlarm() {
    if (!await chrome.alarms.get(ALARM)) {
        await chrome.alarms.create(ALARM, {periodInMinutes: 0.5});
    }
}

chrome.alarms.onAlarm.addListener(alarm => {
    if (alarm.name === ALARM) void check();
});
chrome.runtime.onStartup.addListener(() => { void ensureAlarm(); });
chrome.runtime.onInstalled.addListener(() => { void ensureAlarm(); });
void ensureAlarm();
