// The caller grants one close only after the desktop app displays the countdown.
export async function activeTarget(browser) {
    const window = await browser.windows.getLastFocused({windowTypes: ['normal']});
    if (!window?.focused || window.type !== 'normal' || window.incognito
            || !['normal', 'maximized'].includes(window.state)) {
        return null;
    }
    const tabs = await browser.tabs.query({windowId: window.id});
    const tab = tabs.find(item => item.active);
    if (tabs.length < 2 || !Number.isInteger(tab?.id) || tab.pinned || tab.incognito
            || tab.status !== 'complete') {
        return null;
    }
    return {windowId: window.id, tabId: tab.id};
}

export async function attemptClose({browser, brand, send, wait, revision}) {
    const initialRevision = revision();
    const target = await activeTarget(browser);
    if (!target || revision() !== initialRevision) return false;

    const offer = await send({op: 'arm', browser: brand});
    const token = offer?.token;
    if (typeof token !== 'string' || offer.seconds !== 10) return false;

    async function stillTargeted() {
        const current = await activeTarget(browser);
        return revision() === initialRevision && current?.windowId === target.windowId
            && current.tabId === target.tabId;
    }

    let closed = false;
    try {
        if (!await stillTargeted()) return false;
        for (let second = 0; second < offer.seconds; second += 1) {
            await wait(1000);
            if (!await stillTargeted()) return false;
        }
        const grant = await send({op: 'finish', token});
        if (grant?.close !== true || !await stillTargeted()) return false;
        await browser.tabs.remove(target.tabId);
        closed = true;
        return true;
    } finally {
        if (!closed) await send({op: 'cancel', token});
    }
}
