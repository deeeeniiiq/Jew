const fs = require('node:fs');
const path = require('node:path');

const hasWorkspace = folder => fs.existsSync(path.join(folder, 'data', 'knowledge_graph.sqlite3'));

function preferredUserData(appData, currentProfile) {
  const legacyProfile = path.join(appData, 'clew');
  // A new Jew workspace has precedence even when a Clew database remains.
  if (hasWorkspace(currentProfile)) return currentProfile;
  if (hasWorkspace(legacyProfile)) return legacyProfile;
  return currentProfile;
}

module.exports = { preferredUserData };
