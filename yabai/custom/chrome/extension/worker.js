import { signature, validate, overlaps } from './model.js';
const HOST = 'local.yabai.chrome_layout';
let profile,
  port,
  connecting = false,
  reconnectTimer,
  reconnectAttempt = 0;
function scheduleReconnect() {
  if (reconnectTimer) return;
  const delay = Math.min(1000 * 2 ** Math.min(reconnectAttempt++, 4), 10000);
  reconnectTimer = setTimeout(() => {
    reconnectTimer = undefined;
    connect();
  }, delay);
  // Alarm survives service-worker suspension; timer provides the fast path.
  chrome.alarms.create('reconnect', { delayInMinutes: 0.5 });
}
const uuid = () => crypto.randomUUID().replaceAll('-', '');
async function registry() {
  return (await chrome.storage.session.get('windows')).windows || {};
}
async function snapshot(hints = []) {
  const all = (
    await chrome.windows.getAll({ populate: true, windowTypes: ['normal'] })
  ).filter((w) => !w.incognito);
  // A background profile may legitimately have no current window.
  if (!all.length) {
    await chrome.storage.session.set({ windows: {} });
    return [];
  }
  // Query each explicit window, never depend on Chrome's current-window context.
  const groups = (
    await Promise.all(
      all.map((w) => chrome.tabGroups.query({ windowId: w.id })),
    )
  ).flat();
  const records = await registry();
  const output = all.map((w) => {
    const tabs = [...w.tabs].sort((a, b) => a.index - b.index);
    const ids = [
      ...new Set(tabs.map((t) => t.groupId).filter((i) => i !== -1)),
    ];
    const source = {
      kind: 'chrome-window',
      profile,
      token: records[w.id]?.token || uuid(),
      tabs: tabs.map((t) => ({
        url: t.pendingUrl || t.url || '',
        pinned: t.pinned,
        group: ids.indexOf(t.groupId),
      })),
      groups: ids.map((id) => {
        const g = groups.find((g) => g.id === id);
        if (!g) throw Error('Los grupos cambiaron; vuelve a guardar');
        return { title: g.title || '', color: g.color, collapsed: g.collapsed };
      }),
      active: Math.max(
        0,
        tabs.findIndex((t) => t.active),
      ),
    };
    let unsupported = '';
    try {
      validate(source, profile);
    } catch (error) {
      unsupported = error.message;
    }
    return {
      id: w.id,
      unsupported,
      title: tabs.find((t) => t.active)?.title || '',
      frame: { x: w.left, y: w.top, w: w.width, h: w.height },
      source,
    };
  });
  for (const item of output) {
    if (
      !records[item.id] ||
      !hints.some(
        (h) => h.profile === profile && h.token === records[item.id].token,
      )
    ) {
      const candidates = hints.filter(
        (h) => h.profile === profile && signature(h) === signature(item.source),
      );
      const peers = output.filter(
        (w) => signature(w.source) === signature(item.source),
      );
      if (
        candidates.length === 1 &&
        peers.length === 1 &&
        !Object.values(records).some((r) => r.token === candidates[0].token)
      )
        item.source.token = candidates[0].token;
      records[item.id] = {
        token: item.source.token,
        status: records[item.id]?.status || 'complete',
      };
    }
    item.incomplete = records[item.id].status !== 'complete';
  }
  for (const id of Object.keys(records))
    if (!output.some((w) => String(w.id) === id)) delete records[id];
  await chrome.storage.session.set({ windows: records });
  return output;
}
async function tracked(stage, promise, report) {
  report(stage + ':start');
  const value = await promise;
  report(stage + ':done');
  return value;
}
async function restore(source, report = () => {}) {
  validate(source, profile);
  const current = await tracked('snapshot', snapshot([source]), report);
  let existing = current.filter((w) => w.source.token === source.token);
  if (!existing.length)
    existing = current.filter((w) => signature(w.source) === signature(source));
  if (existing.length > 1)
    throw Error('Varias ventanas Chrome idénticas: no se elige una al azar');
  if (existing.length === 1) {
    if (existing[0].incomplete)
      throw Error(
        'Apertura anterior incompleta; revisa esa ventana antes de reintentar',
      );
    const records = await registry();
    records[existing[0].id] = { token: source.token, status: 'complete' };
    await chrome.storage.session.set({ windows: records });
    return { reused: true, window: existing[0].id };
  }
  if (current.some((w) => overlaps(w.source, source)))
    throw Error(
      'Hay una ventana Chrome parcialmente coincidente; no se duplican sus pestañas',
    );
  const pending = (await chrome.storage.session.get('pendingRestores')).pendingRestores || {};
  if (pending[source.token])
    throw Error('Apertura anterior sin confirmar; no se crea otra ventana');
  // Persist intent BEFORE windows.create, whose response may never arrive.
  pending[source.token] = true;
  await chrome.storage.session.set({ pendingRestores: pending });
  // Never close or alter pre-existing windows. A failed new window remains for inspection.
  const window = await tracked('windows.create', chrome.windows.create({
    url: 'about:blank',
    focused: false,
    type: 'normal',
  }), report);
  const records = await registry();
  records[window.id] = { token: source.token, status: 'building' };
  await chrome.storage.session.set({ windows: records });
  try {
    const ids = [];
    for (let i = 0; i < source.tabs.length; i++) {
      const t = source.tabs[i];
      const tab =
        i === 0
          ? await tracked('tabs.update', chrome.tabs.update(window.tabs[0].id, {
              url: t.url,
              pinned: t.pinned,
            }), report)
          : await tracked('tabs.create', chrome.tabs.create({
              windowId: window.id,
              url: t.url,
              pinned: t.pinned,
              active: false,
              index: i,
            }), report);
      ids.push(tab.id);
    }
    const groupIds = [];
    for (let i = 0; i < source.groups.length; i++) {
      const id = await tracked('tabs.group', chrome.tabs.group({
        createProperties: { windowId: window.id },
        tabIds: ids.filter((_, n) => source.tabs[n].group === i),
      }), report);
      groupIds.push(id);
      await tracked('tabGroups.update', chrome.tabGroups.update(id, {
        title: source.groups[i].title,
        color: source.groups[i].color,
      }), report);
    }
    await tracked('tabs.update', chrome.tabs.update(ids[source.active], { active: true }), report);
    for (let i = 0; i < groupIds.length; i++)
      await tracked('tabGroups.update', chrome.tabGroups.update(groupIds[i], {
        collapsed: source.groups[i].collapsed,
      }), report);
    const actual = (await tracked('tabs.query', chrome.tabs.query({ windowId: window.id }), report)).sort(
      (a, b) => a.index - b.index,
    );
    if (
      actual.length !== ids.length ||
      actual.some(
        (t, i) =>
          t.id !== ids[i] ||
          t.pinned !== source.tabs[i].pinned ||
          t.groupId !==
            (source.tabs[i].group < 0 ? -1 : groupIds[source.tabs[i].group]),
      )
    )
      throw Error('Chrome cambió el orden/grupos durante la apertura');
    records[window.id].status = 'complete';
    await chrome.storage.session.set({ windows: records });
    delete pending[source.token];
    await chrome.storage.session.set({ pendingRestores: pending });
    return { reused: false, window: window.id };
  } catch (error) {
    throw Error(
      'Ventana nueva incompleta: ' +
        error.message +
        '. No se cerró ninguna ventana.',
    );
  }
}
async function connect() {
  if (port || connecting) return;
  connecting = true;
  try {
    const saved = await chrome.storage.local.get('profile');
    profile = saved.profile || uuid();
    if (!saved.profile) await chrome.storage.local.set({ profile });
    port = chrome.runtime.connectNative(HOST);
    port.onDisconnect.addListener(() => {
      const message =
        chrome.runtime.lastError?.message || 'Puente desconectado';
      port = null;
      chrome.action.setBadgeText({ text: '!' });
      chrome.action.setTitle({ title: message });
      scheduleReconnect();
    });
    port.onMessage.addListener(async (msg) => {
      if (msg.type === 'ready') {
        reconnectAttempt = 0;
        clearTimeout(reconnectTimer);
        reconnectTimer = undefined;
        await chrome.action.setBadgeText({ text: 'OK' });
        await chrome.action.setTitle({
          title: 'Conectado: guarda el layout con tu atajo habitual',
        });
        return;
      }
      if (msg.type !== 'request') return;
      const activePort = port;
      try {
        const result =
          msg.action === 'snapshot'
            ? await snapshot(msg.hints || [])
            : msg.action === 'restore'
              ? await restore(msg.source, (stage) => {
                  try { activePort.postMessage({type:'progress', id:msg.id, stage}); } catch {}
                })
              : (() => {
                  throw Error('Acción no permitida');
                })();
        const response = { id: msg.id, ok: true, result };
        if (new TextEncoder().encode(JSON.stringify(response)).length > 890000)
          throw Error('Demasiadas pestañas para un mensaje local');
        activePort.postMessage(response);
      } catch (error) {
        activePort?.postMessage({
          id: msg.id,
          ok: false,
          error: error.message,
        });
      }
    });
    port.postMessage({ type: 'hello', profile });
  } catch (error) {
    port = null;
    scheduleReconnect();
  } finally {
    connecting = false;
  }
}
chrome.runtime.onStartup.addListener(connect);
chrome.runtime.onInstalled.addListener(connect);
chrome.action.onClicked.addListener(connect);
chrome.alarms.onAlarm.addListener((a) => {
  if (a.name === 'reconnect') connect();
});
connect();
