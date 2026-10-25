const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { preferredUserData } = require('../profile.cjs');

test('Jew prefers its own database and reuses Clew only when needed', () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'jew-profile-test-'));
  const jew = path.join(root, 'jew');
  const clew = path.join(root, 'clew');
  const createDatabase = folder => {
    fs.mkdirSync(path.join(folder, 'data'), { recursive: true });
    fs.writeFileSync(path.join(folder, 'data', 'knowledge_graph.sqlite3'), 'synthetic');
  };
  try {
    assert.equal(preferredUserData(root, jew), jew);
    createDatabase(clew);
    assert.equal(preferredUserData(root, jew), clew);
    createDatabase(jew);
    assert.equal(preferredUserData(root, jew), jew);
    assert.equal(fs.readFileSync(path.join(clew, 'data', 'knowledge_graph.sqlite3'), 'utf8'), 'synthetic');
    assert.equal(fs.readFileSync(path.join(jew, 'data', 'knowledge_graph.sqlite3'), 'utf8'), 'synthetic');
  } finally {
    fs.rmSync(root, { recursive: true, force: true });
  }
});
