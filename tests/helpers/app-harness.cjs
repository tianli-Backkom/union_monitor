const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

// The app's real router, selectors and render functions run unchanged. Only
// browser DOM/network boundaries are doubled; Chromium covers actual layout.
function createApp({ fetch, setTimeout, clearTimeout } = {}) {
  const elements = new Map();
  function element(id) {
    if (!elements.has(id)) {
      const node = {
        id, hidden: ['workbench-view', 'project-task-view', 'triton-view', 'method-view', 'ubs-repo-view'].includes(id),
        innerHTML: '', textContent: '', value: '', title: '', open: false, children: [],
        close() { this.open = false; }, showModal() { this.open = true; },
        querySelectorAll() { return []; }, querySelector() { return null; },
        closest() { return this; }, setAttribute(name, value) { this[name] = value; },
        addEventListener() {}, remove() {}, prepend() {},
      };
      elements.set(id, node);
    }
    return elements.get(id);
  }
  const context = {
    document: { getElementById: element, querySelectorAll: () => [], title: '' },
    window: {}, location: { hash: '#ubs' },
    history: { pushState(_s, _t, hash) { context.location.hash = hash; }, replaceState(_s, _t, hash) { context.location.hash = hash; } },
    Metrics: require('../../web/core.js'), Router: require('../../web/router.js'),
    Catalog: require('../../web/catalog.js'), Units: require('../../web/units.js'),
    URL, AbortController, console, fetch: fetch || (async () => { throw new Error('unexpected network read'); }),
    setTimeout: setTimeout || globalThis.setTimeout, clearTimeout: clearTimeout || globalThis.clearTimeout,
  };
  vm.createContext(context);
  const source = fs.readFileSync(path.join(__dirname, '../../web/app.js'), 'utf8');
  const wiring = source.indexOf("\nfor(const id of ['query','state','qualityFilter','triggerFilter'])");
  if (wiring < 0) throw new Error('app event wiring marker missing');
  vm.runInContext(source.slice(0, wiring), context);
  return { context, element, run(code) { return vm.runInContext(code, context); } };
}

module.exports = { createApp };
