// Offline tests for the actual browser script; no package dependencies.
const { readFileSync } = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const code = readFileSync('docs/launch.js', 'utf8');
for (const raw of [undefined, '', 'invalid', 'javascript:alert(1)', 'http://app.example.org',
                   'https://user:secret@app.example.org', 'https://app.example.org/?token=x',
                   'https://app.example.org/#secret']) {
  const link = { removeAttribute() { throw new Error('Enabled invalid destination'); } };
  const context = vm.createContext({ URL });
  vm.runInContext(code, context);
  context.configureLaunch(raw, link, {});
  assert.equal(link.href, undefined);
}
const context = vm.createContext({ URL });
vm.runInContext(code, context);
const removed = [];
const link = { removeAttribute(name) { removed.push(name); } };
const status = {};
context.configureLaunch('https://verified.example.org/pap', link, status);
assert.equal(link.href, 'https://verified.example.org/pap');
assert.deepEqual(removed, ['aria-disabled', 'tabindex']);
assert.match(status.textContent, /Open the platform/);
console.log('Launch configuration tests passed');
