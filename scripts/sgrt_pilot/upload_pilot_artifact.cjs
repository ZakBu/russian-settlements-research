/* Publish an already computed, catalogue-pinned archive using GitHub-owned
 * artifact staging. The runner's runtime token never leaves its official SDK.
 * Entry point is a JavaScript action, not a shell step, for runtime bindings.
 */
'use strict';
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const {execFileSync} = require('node:child_process');
const staging = require('./actions_artifact_staging.cjs');
function gh(args) { return execFileSync('gh', args, {encoding:'utf8', maxBuffer:4*1024*1024}); }
function sha(file) { return crypto.createHash('sha256').update(fs.readFileSync(file)).digest('hex'); }
async function main() {
  const root = process.env.GITHUB_WORKSPACE;
  const catalogFile = path.join(root, 'data/pilot_catalog_20261024.json');
  const catalog = JSON.parse(fs.readFileSync(catalogFile, 'utf8'));
  const asset = catalog.assets[0];
  const repo = process.env.GITHUB_REPOSITORY;
  if (repo !== 'ZakBu/russian-settlements-research' || catalog.repository !== repo) throw new Error('Unexpected repository');
  const tag = catalog.release_tag;
  if (!/^sgrt-pilot-\d{8}-v\d+$/.test(tag)) throw new Error('Unexpected pilot release tag');
  const endpoint = `repos/${repo}/releases/tags/${tag}`;
  let release = JSON.parse(gh(['api', endpoint]));
  if (!release.draft) throw new Error('Refusing to replace a published release');
  Object.assign(process.env, {SGRT_STAGING_NAME:'sgrt-pilot-payload',
    SGRT_STAGING_BYTES:String(asset.bytes), SGRT_STAGING_SHA256:asset.sha256});
  await staging.reserve();
  const marker = `<!-- sgrt-pilot-upload-ready:${asset.sha256} -->`;
  let ready = false;
  for (let attempt=0; attempt<120; attempt++) {
    release = JSON.parse(gh(['api', endpoint]));
    if (!release.draft) throw new Error('Release was published during staging');
    if ((release.body || '').includes(marker)) { ready=true; break; }
    await new Promise(resolve => setTimeout(resolve, 10000));
  }
  if (!ready) throw new Error('Exact archive was not supplied within20minutes');
  process.env.SGRT_UPLOAD_READY_SHA256=asset.sha256;
  const archive = await staging.finalize();
  const atlas = path.join(path.dirname(archive), 'pilot_atlas.pdf');
  const row = catalog.files.find(r => r.path.endsWith('/outputs/pilot_atlas.pdf'));
  if (!row) throw new Error('Atlas missing from catalogue');
  execFileSync('python3', ['-c',
    'import zipfile,sys,shutil\nwith zipfile.ZipFile(sys.argv[1]) as z, z.open("objects/"+sys.argv[2]) as s, open(sys.argv[3],"wb") as d: shutil.copyfileobj(s,d)',
    archive,row.blob,atlas]);
  if (sha(atlas) !== catalog.objects[row.blob].sha256) throw new Error('Atlas failed checksum');
  const uploadCatalog = path.join(path.dirname(archive),'pilot_catalog.json');
  fs.copyFileSync(catalogFile,uploadCatalog);
  gh(['release','upload',tag,archive,atlas,uploadCatalog,'--repo',repo,'--clobber']);
  release=JSON.parse(gh(['api',endpoint]));
  for (const [name,file] of [['sgrt-pilot-data.zip',archive],['pilot_atlas.pdf',atlas],['pilot_catalog.json',uploadCatalog]]) {
    const remote = release.assets.find(a=>a.name===name);
    if (!remote || remote.size!==fs.statSync(file).size) throw new Error('Release upload size mismatch');
    if (remote.digest && remote.digest!==`sha256:${sha(file)}`) throw new Error('Release upload digest mismatch');
  }
  const edit=path.join(path.dirname(archive),'publish.json');
  fs.writeFileSync(edit,JSON.stringify({draft:false,make_latest:'false',body:(release.body||'').replace(marker,'').trim()}));
  gh(['api','--method','PATCH',`repos/${repo}/releases/${release.id}`,'--input',edit]);
  console.log(`Published catalogue-pinned pilot ${tag}; archive SHA256 ${asset.sha256}`);
}
module.exports={main};
