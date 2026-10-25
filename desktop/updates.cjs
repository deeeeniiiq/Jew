// No upstream Clew update channel may be used for Jew builds. Configure an
// independently published Jew repository when a real release channel exists.

function versionParts(value) {
  if (typeof value !== 'string' || !/^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$/.test(value)) {
    throw new Error('Invalid stable release version.');
  }
  const parts = value.split('.').map(Number);
  if (!parts.every(Number.isSafeInteger)) throw new Error('Invalid stable release version.');
  return parts;
}

async function checkLatestRelease(currentVersion, platform, arch, request = fetch, repository = process.env.JEW_RELEASE_REPOSITORY) {
  if (!repository || !/^[A-Za-z0-9-]+\/[A-Za-z0-9_.-]+$/.test(repository) || /\/Clew$/i.test(repository)) {
    throw new Error('Automatic updates are unavailable until an official Jew release repository is configured.');
  }
  const releases = `https://github.com/${repository}/releases`;
  const api = `https://api.github.com/repos/${repository}/releases/latest`;
  const current = versionParts(currentVersion);
  const response = await request(api, {
    headers: { Accept: 'application/vnd.github+json', 'User-Agent': `Jew/${currentVersion}` },
    signal: AbortSignal.timeout(15000), redirect: 'error'
  });
  if (response.status === 404) throw new Error('There is no published stable release yet.');
  if (!response.ok) throw new Error(`GitHub release check returned HTTP ${response.status}. Try again later.`);
  const text = await response.text();
  if (text.length > 1024 * 1024) throw new Error('Release metadata is too large.');
  const release = JSON.parse(text);
  const version = typeof release.tag_name === 'string' ? release.tag_name.replace(/^v/, '') : '';
  const latest = versionParts(version);
  const url = `${releases}/tag/v${version}`;
  if (release.draft || release.prerelease || release.tag_name !== `v${version}` || release.html_url !== url || !Array.isArray(release.assets)) {
    throw new Error('GitHub returned an invalid stable release contract.');
  }
  const os = { darwin: 'mac', win32: 'win', linux: 'linux' }[platform];
  const extension = { darwin: 'dmg', win32: 'exe', linux: 'AppImage' }[platform];
  const asset = `Jew-${version}-${os}-${arch}.${extension}`;
  if (!os || !['x64', 'arm64'].includes(arch) || !release.assets.some(item => item.name === asset)) {
    throw new Error('The latest release has no installer for this platform and architecture.');
  }
  const difference = latest.map((part, index) => part - current[index]).find(value => value !== 0) ?? 0;
  return { available: difference > 0, version, url };
}

module.exports = { checkLatestRelease };
