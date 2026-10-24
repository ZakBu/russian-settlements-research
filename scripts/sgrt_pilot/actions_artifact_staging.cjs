/* Task-scoped exact-file staging through the owning GitHub Actions artifact store.
 * Run ONLY inside the same JavaScript-action job for reserve and finalize.
 * npm install --prefix "$RUNNER_TEMP/artifact-sdk" @actions/artifact@2.3.2
 * NODE_PATH="$RUNNER_TEMP/artifact-sdk/node_modules"
 * Uses pinned official SDK internals: CreateArtifact version4, FinalizeArtifact,
 * GetSignedArtifactURL. Runtime JWT is read only by the SDK and never exported.
 * No workflow, repository variable, release or permission change occurs here.
 */
'use strict';
const fs = require('node:fs');
const path = require('node:path');
const https = require('node:https');
const crypto = require('node:crypto');
const {Transform} = require('node:stream');
const {pipeline} = require('node:stream/promises');

function sdk() {
  const lib = path.dirname(require.resolve('@actions/artifact'));
  const info = require(path.join(lib, '..', 'package.json'));
  if (info.version !== '2.3.2') throw new Error('Unexpected artifact SDK version');
  return {
    artifact: require('@actions/artifact').default,
    core: require(require.resolve('@actions/core', {paths: [lib]})),
    ids: require(path.join(lib, 'internal/shared/util.js')).getBackendIdsFromToken,
    client: require(path.join(lib, 'internal/shared/artifact-twirp-client.js')).internalArtifactTwirpClient,
    StringValue: require(path.join(lib, 'generated/index.js')).StringValue,
  };
}

function metadata(env = process.env) {
  const name = env.SGRT_STAGING_NAME || '';
  const size = env.SGRT_STAGING_BYTES || '';
  const sha256 = env.SGRT_STAGING_SHA256 || '';
  if (!/^[A-Za-z0-9._-]{1,100}$/.test(name)) throw new Error('Invalid staging artifact name');
  if (!/^[1-9][0-9]*$/.test(size) || !Number.isSafeInteger(Number(size))) throw new Error('Invalid staging size');
  if (!/^[a-f0-9]{64}$/.test(sha256)) throw new Error('Invalid staging SHA256');
  if (env.GITHUB_REPOSITORY !== 'ZakBu/russian-settlements-research') throw new Error('Unexpected repository');
  if (!env.RUNNER_TEMP || !env.GITHUB_RUN_ID) throw new Error('GitHub runner environment required');
  return {name, size, sha256, repository: env.GITHUB_REPOSITORY, runId: env.GITHUB_RUN_ID};
}

function privatePath(file) {
  const folder = path.join(process.env.RUNNER_TEMP, 'sgrt-exact-staging');
  fs.mkdirSync(folder, {recursive: true, mode: 0o700});
  return path.join(folder, file);
}

function maskedBlobURL(value, core) {
  // Register the whole capability as well as both encodings of its signature.
  // Never place it in a log, workflow output, git file or release body.
  core.setSecret(value);
  const url = new URL(value);
  if (url.protocol !== 'https:' || !url.hostname.endsWith('.blob.core.windows.net')) {
    throw new Error('Artifact service returned unexpected blob storage host');
  }
  const sig = url.searchParams.get('sig');
  if (!sig) throw new Error('Missing artifact SAS signature');
  core.setSecret(sig);
  core.setSecret(encodeURIComponent(sig));
  return url;
}

async function reserve() {
  const {artifact, core, ids, client} = sdk();
  const m = metadata();
  const backend = ids();
  const response = await client().CreateArtifact({...backend, name: m.name, version: 4});
  if (!response.ok || !response.signedUploadUrl) throw new Error('CreateArtifact rejected reservation');
  maskedBlobURL(response.signedUploadUrl, core);
  const stateFile = privatePath('reservation.json');
  fs.writeFileSync(stateFile, JSON.stringify({...m, ...backend}), {mode: 0o600, flag: 'wx'});
  const controlFile = privatePath('transfer.json');
  // This short-lived capability is transferred only in a separate authorized
  // Actions artifact. Its name/id are public metadata; its bytes are never logged.
  fs.writeFileSync(controlFile, JSON.stringify({
    schema: 'sgrt.github_actions_exact_staging.v1', ...m,
    archiveName: 'sgrt-pilot-data.zip', archiveBytes: Number(m.size),
    archiveSha256: m.sha256, releaseTag: process.env.SGRT_RELEASE_TAG || null,
    artifactName: m.name,
    signedUploadUrl: response.signedUploadUrl,
  }), {mode: 0o600, flag: 'wx'});
  const controlName = `${m.name}-control`;
  let control;
  try {
    control = await artifact.uploadArtifact(controlName, [controlFile], path.dirname(controlFile), {
      retentionDays: 1, compressionLevel: 0,
    });
  } finally {
    fs.rmSync(controlFile, {force: true});
  }
  core.setOutput('staging-control-artifact-name', controlName);
  core.setOutput('staging-control-artifact-id', String(control.id));
  core.info(`Reserved task-owned staging artifact; control artifact ID ${control.id}`);
}

function getBlob(url) {
  return new Promise((resolve, reject) => {
    const request = https.get(url, response => {
      if (response.statusCode !== 200) {
        response.resume();
        reject(new Error(`Artifact blob download HTTP ${response.statusCode}`));
      } else resolve(response);
    });
    request.setTimeout(120000, () => request.destroy(new Error('Artifact download timed out')));
    request.on('error', () => reject(new Error('Artifact blob download failed')));
  });
}

async function finalize() {
  const {core, ids, client, StringValue} = sdk();
  const m = metadata();
  const state = JSON.parse(fs.readFileSync(privatePath('reservation.json'), 'utf8'));
  const backend = ids();
  for (const key of ['name', 'size', 'sha256', 'repository', 'runId']) {
    if (m[key] !== state[key]) throw new Error('Staging metadata changed between reservation and finalization');
  }
  for (const key of ['workflowRunBackendId', 'workflowJobRunBackendId']) {
    if (backend[key] !== state[key]) throw new Error('Artifact must be finalized by the reserving workflow job');
  }
  // The calling workflow must first observe its exact public upload-ready marker.
  // Finalization itself does not certify remote bytes; the download/hash check does.
  if (process.env.SGRT_UPLOAD_READY_SHA256 !== m.sha256) throw new Error('Exact upload-ready marker required');
  const rpc = client();
  const response = await rpc.FinalizeArtifact({
    ...backend, name: m.name, size: m.size,
    hash: StringValue.create({value: `sha256:${m.sha256}`}),
  });
  if (!response.ok || !response.artifactId) throw new Error('FinalizeArtifact rejected upload');
  const download = await rpc.GetSignedArtifactURL({...backend, name: m.name});
  if (!download.signedUrl) throw new Error('Artifact download URL unavailable');
  const url = maskedBlobURL(download.signedUrl, core);
  const target = privatePath('sgrt-pilot-data.zip');
  const temporary = `${target}.partial`;
  const hash = crypto.createHash('sha256');
  let size = 0;
  const checker = new Transform({transform(chunk, encoding, callback) {
    size += chunk.length;
    hash.update(chunk);
    callback(null, chunk);
  }});
  try {
    await pipeline(await getBlob(url), checker, fs.createWriteStream(temporary, {mode: 0o600, flags: 'wx'}));
    if (String(size) !== m.size || hash.digest('hex') !== m.sha256) throw new Error('Staged artifact failed exact-file integrity check');
    fs.renameSync(temporary, target);
  } catch (error) {
    fs.rmSync(temporary, {force: true});
    throw error;
  }
  core.setOutput('staging-artifact-id', String(response.artifactId));
  core.setOutput('staging-verified-zip', target);
  core.info(`Exact staging complete: ${size} bytes, SHA256 ${m.sha256}`);
  return target;
}

module.exports = {reserve, finalize, metadata};
if (require.main === module) {
  const command = process.argv[2];
  if (!['reserve', 'finalize'].includes(command)) {
    process.stderr.write('Usage: actions_artifact_staging.cjs reserve|finalize\n');
    process.exitCode = 2;
  } else {
    ({reserve, finalize}[command])().catch(() => {
      // Do not propagate SDK/network exceptions that could contain a capability.
      process.stderr.write('Task-owned artifact staging failed; no credential details logged.\n');
      process.exitCode = 1;
    });
  }
}
