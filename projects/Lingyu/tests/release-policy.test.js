const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { spawnSync } = require('node:child_process');

const projectRoot = path.join(__dirname, '..');
const releasePolicyScript = path.join(projectRoot, 'scripts', 'release-policy.js');
const entitlementsPath = path.join(projectRoot, 'build', 'entitlements.mac.plist');
const readmePath = path.join(projectRoot, 'README.md');
const packageVersion = require(path.join(projectRoot, 'package.json')).version;
const packageConfig = require(path.join(projectRoot, 'package.json'));

function runReleasePolicy(t, environment) {
  const outputDir = fs.mkdtempSync(path.join(os.tmpdir(), 'todo-panel-release-policy-'));
  const outputPath = path.join(outputDir, 'github-output.txt');
  t.after(() => fs.rmSync(outputDir, { recursive: true, force: true }));

  const result = spawnSync(process.execPath, [releasePolicyScript], {
    cwd: projectRoot,
    encoding: 'utf8',
    env: {
      ...process.env,
      GITHUB_OUTPUT: outputPath,
      ...environment,
    },
  });

  return {
    ...result,
    output: fs.existsSync(outputPath) ? fs.readFileSync(outputPath, 'utf8') : '',
  };
}

test('manual workflow runs validate the package without publishing a release', (t) => {
  const result = runReleasePolicy(t, {
    GITHUB_EVENT_NAME: 'workflow_dispatch',
    GITHUB_REF_TYPE: 'branch',
    GITHUB_REF_NAME: 'main',
  });

  assert.equal(result.status, 0, result.stderr);
  assert.match(result.output, /^publish=false$/m);
  assert.match(result.output, new RegExp(`^version=${packageVersion.replaceAll('.', '\\.')}$`, 'm'));
});

test('a matching semantic version tag enables release publishing', (t) => {
  const result = runReleasePolicy(t, {
    GITHUB_EVENT_NAME: 'push',
    GITHUB_REF_TYPE: 'tag',
    GITHUB_REF_NAME: `v${packageVersion}`,
  });

  assert.equal(result.status, 0, result.stderr);
  assert.match(result.output, /^publish=true$/m);
  assert.match(result.output, new RegExp(`^version=${packageVersion.replaceAll('.', '\\.')}$`, 'm'));
});

test('a pushed version tag that disagrees with package.json is rejected', (t) => {
  const result = runReleasePolicy(t, {
    GITHUB_EVENT_NAME: 'push',
    GITHUB_REF_TYPE: 'tag',
    GITHUB_REF_NAME: 'v9.9.9',
  });

  assert.notEqual(result.status, 0);
  assert.equal(
    result.stderr,
    `package.json version ${packageVersion} does not match tag v9.9.9\n`
  );
  assert.equal(result.output, '');
});

test('macOS packaging declares the Electron 44 minimum and least-privilege runtime entitlements', () => {
  const entitlements = fs.readFileSync(entitlementsPath, 'utf8');
  const readme = fs.readFileSync(readmePath, 'utf8');

  assert.equal(packageConfig.build.mac.minimumSystemVersion, '13.0');
  assert.match(readme, /macOS 13(?:\.0)?\+/);
  assert.doesNotMatch(entitlements, /com\.apple\.security\.cs\.allow-dyld-environment-variables/);
  assert.doesNotMatch(entitlements, /com\.apple\.security\.cs\.disable-executable-page-protection/);
  assert.match(entitlements, /com\.apple\.security\.cs\.allow-jit/);
  assert.match(entitlements, /com\.apple\.security\.cs\.disable-library-validation/);
});

test('source archive metadata points to the user project and versions stay aligned', () => {
  const readme = fs.readFileSync(readmePath, 'utf8');
  const lock = require(path.join(projectRoot, 'package-lock.json'));
  assert.equal(lock.version, packageVersion);
  assert.equal(lock.packages[''].version, packageVersion);
  assert.equal(packageConfig.repository.url, 'https://github.com/Freya-Qian/Freya-Qian.git');
  assert.equal(packageConfig.repository.directory, 'projects/Lingyu');
  assert.ok(readme.includes(`当前归档版本：${packageVersion}`));
  assert.doesNotMatch(readme, /xiaopu-ai\/TO-DO-Panel\/releases/);
});
