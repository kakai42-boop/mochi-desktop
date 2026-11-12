import assert from 'node:assert/strict';
import {test} from 'node:test';
import {attemptClose} from '../src/mochi/windows/browser_extension/mood.mjs';

function fixture() {
    const win = {id: 20, focused: true, type: 'normal', state: 'normal', incognito: false};
    const target = {id: 10, active: true, status: 'complete', pinned: false, incognito: false};
    const other = {id: 11, active: false, status: 'complete'};
    const tabs = [target, other];
    const removed = [];
    const requests = [];
    let version = 0;
    const options = {
        browser: {
            windows: {getLastFocused: async () => win},
            tabs: {query: async () => tabs, remove: async id => removed.push(id)},
        },
        brand: 'chrome',
        revision: () => version,
        wait: async () => {},
        send: async request => {
            requests.push(request);
            if (request.op === 'arm') return {token: 'one-use', seconds: 10};
            if (request.op === 'finish') return {close: true};
            return {};
        },
    };
    return {win, target, other, tabs, removed, requests, options, invalidate: () => version++};
}

test('closes the exact captured tab after ten waits and a grant', async () => {
    const f = fixture();
    const waits = [];
    f.options.wait = async ms => waits.push(ms);
    assert.equal(await attemptClose(f.options), true);
    assert.deepEqual(f.removed, [10]);
    assert.deepEqual(waits, Array(10).fill(1000));
    assert.deepEqual(f.requests, [{op: 'arm', browser: 'chrome'}, {op: 'finish', token: 'one-use'}]);
});

for (const [name, change] of Object.entries({
    fullscreen: f => { f.win.state = 'fullscreen'; },
    lockedFullscreen: f => { f.win.state = 'locked-fullscreen'; },
    private: f => { f.win.incognito = true; },
    pinned: f => { f.target.pinned = true; },
    last: f => { f.tabs.pop(); },
    background: f => { f.win.focused = false; },
    loading: f => { f.target.status = 'loading'; },
})) {
    test(`does not arm a protected target: ${name}`, async () => {
        const f = fixture();
        change(f);
        assert.equal(await attemptClose(f.options), false);
        assert.deepEqual(f.requests, []);
    });
}

for (const [name, change] of Object.entries({
    switchedTab: f => { f.target.active = false; f.other.active = true; },
    fullscreen: f => { f.win.state = 'fullscreen'; },
    focus: f => { f.win.focused = false; },
    navigationEvent: f => f.invalidate(),
})) {
    test(`cancels during the countdown: ${name}`, async () => {
        const f = fixture();
        f.options.wait = async () => change(f);
        assert.equal(await attemptClose(f.options), false);
        assert.deepEqual(f.requests.map(r => r.op), ['arm', 'cancel']);
        assert.deepEqual(f.removed, []);
    });
}

test('rechecks the target after receiving a grant', async () => {
    const f = fixture();
    const send = f.options.send;
    f.options.send = async message => {
        if (message.op === 'finish') f.target.pinned = true;
        return send(message);
    };
    assert.equal(await attemptClose(f.options), false);
    assert.deepEqual(f.removed, []);
});

test('no grant means no close', async () => {
    const f = fixture();
    const send = f.options.send;
    f.options.send = async message => message.op === 'finish' ? {} : send(message);
    assert.equal(await attemptClose(f.options), false);
    assert.deepEqual(f.removed, []);
});
