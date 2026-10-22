"""Reorganize the repository into current / archive / removed.

Run from the repository root on a clean checkout. Writes
.agent-ops/plan.json (every move and removal) and .agent-ops/removed.txt
(paths to pack into the archive release before they leave the tree).
--apply performs git mv / git rm and rewrites Markdown links.
"""
import argparse
import json
import os
import posixpath
import re
import subprocess
import sys

ROOT_KEEP = {
    'AGENTS.md', 'AI_START_HERE.md', 'README.md', 'POPULATION_BASE.md', 'decisions.json',
    '.gitignore', 'requirements-handoff.txt', 'requirements-mass-linkage.txt',
    'requirements-pilot.txt', 'requirements-population.txt',
}
ROOT_REMOVE = {
    'repository_inventory.json', 'repository_policy.json',
    'research_context/navigation.json', 'research_context/restoration_manifest.json',
    'research_context/original_root_README_85aebaf.md', 'research_context/INDEX.md',
    'research_context/reviews/early_core_read_20261022.json',
    'research_context/reviews/handoff_guardian_20261022.json',
    'research_context/reviews/public_handoff_verification_20261022.json',
    'references/history_cleanup_plan.json', 'references/history_commit_map.csv',
    'references/history_verification.json',
}
ROOT_MOVES = {
    'METHODOLOGY.md': 'docs/census_base/METHODOLOGY.md',
    'SOURCES.md': 'docs/census_base/SOURCES.md',
    'STATUS.md': 'archive/census_base_2026-10/STATUS.md',
    'docs/DECISION_DIARY.md': 'docs/census_base/DECISION_DIARY.md',
    'docs/PARSER_LESSONS.md': 'docs/census_base/PARSER_LESSONS.md',
}
# Process-only reports of the census work (packaging receipts, not findings).
DOCS_REMOVE = {
    'docs/CONSOLIDATED_PACKAGE_20261003.md', 'docs/CONTINUATION_PACKAGE_20261003.md',
    'docs/MASS_LOOP_PACKAGE_20261003.md', 'docs/RESEARCH_AGENT_METHODS.md',
}

WC = 'research/sgrt_word_completion_20261021/'
CURRENT_SGRT = [
    (WC + 'literature/cycle08_functional_gravity_20261022/MODEL_DESIGN_RU.md', 'sgrt/MODEL_DESIGN.md'),
    (WC + 'literature/cycle08_functional_gravity_20261022/', 'sgrt/literature/functional_gravity/'),
    (WC + 'literature/cycle07_classics_final/', 'sgrt/literature/classics/'),
    (WC + 'literature/cycle07_delimitation/', 'sgrt/literature/delimitation/'),
    (WC + 'literature/methodological_review_addendum.md', 'sgrt/literature/classics_addendum.md'),
    (WC + 'reviews/cycle06/word_requirement_tracking/', 'sgrt/word_requirements/'),
]

# Agent review/coordination folders: their written findings (Markdown) are kept,
# the generated checks, receipts and tables are not.
REVIEW_DIRS = re.compile(r'/(reviews|review|supervision|critic)/')
PROCESS_DIRS = re.compile(
    r'/(coordination|delivery|replay_logs|output|published|figures|'
    r'reproducibility_cycle05|reproducibility_cycle06|relinked|relinked_v3|history_v\d)/'
    r'|/(analysis|maps)/history/')
KEEP_FROM_PROCESS = {
    WC + 'delivery/cycle07_current_primary_v1/report_v2/SGRT_RESEARCH_REPORT.md',
    WC + 'delivery/cycle07_current_primary_v1/report_v2/SUPERVISOR_BRIEF.md',
    WC + 'coordination/cycle07_reproduction/REPRODUCE_RU.md',
}
PROCESS_FILES = re.compile(
    r'(REPLAY|TASK_CONTRACT|STATISTICAL_REVIEW_CONTRACT|decision_contract|ACCEPTANCE_PROTOCOL|'
    r'REVIEW_STATUS|FINAL_REPORT_REVIEW|^REPORT_REVIEW|^CURRENT_REVIEW|JOURNAL\.md$|EXECUTION_LOG|'
    r'ACCESS_LOG|loop_policy|design_guardrails|ADJUDICATION|scope_notes|'
    r'make_package|render_report|render_pdf|package_deliverables|build_claim_registry|'
    r'newsource060_interpretation_(pending_v1|v1|v2)\.md$|'
    r'PACKAGE_|ARTIFACT_MANIFEST|PUBLICATION_FILES|VISUAL_AUDIT|ENVIRONMENT\.json|'
    r'runtime_versions|CODE_PARSE_CHECK|FIGURE_FORMAT_CHECK|VERIFICATION_SUMMARY|'
    r'PRIMARY_INPUT_RECHECK|SOURCE_DOCUMENT_PROVENANCE|CENSUS1989_COVERAGE_AUDIT|DOWNLOADS\.md$)')
TEXT_KEEP = ('.md', '.py', '.yaml', '.yml', '.txt', '.sql', '.ipynb')
SMALL_TABLE_NAMES = re.compile(r'(BIBLIOGRAPHY|bibliography|sources?|claims?_registry)', re.I)
WORKFLOWS = '.github/'


def git_files():
    out = subprocess.check_output(['git', 'ls-files', '-z'])
    return [p.decode() for p in out.split(b'\0') if p]


def population_inputs():
    manifest = json.load(open('research_context/population_source_manifest.json'))
    return {r['path'] for r in manifest['inputs']}


def classify(files):
    pop = population_inputs()
    moves, removes = {}, set()
    for f in files:
        if f.startswith(WORKFLOWS) or f.startswith('.agent-ops/'):
            continue
        if f in ROOT_REMOVE or f in DOCS_REMOVE:
            removes.add(f); continue
        if f in ROOT_MOVES:
            moves[f] = ROOT_MOVES[f]; continue
        if f in ROOT_KEEP or f in pop:
            continue
        top = f.split('/')[0]
        if top in {'scripts', 'tests', 'config', 'data', 'references', 'research_audit'}:
            continue
        if top == 'research_context':
            continue
        if top == 'docs':
            moves[f] = 'archive/census_base_2026-10/reports/' + f[len('docs/'):]
            continue
        if top == 'publication':
            moves[f] = 'archive/census_base_2026-10/' + f
            continue
        if top == 'research_rebuild':
            if f.startswith('research_rebuild/evidence/') and not f.endswith(('.md', '.py', '.sql', '.ipynb')):
                removes.add(f)
            continue
        if top == 'research':
            target = None
            for src, dst in CURRENT_SGRT:
                if f == src or (src.endswith('/') and f.startswith(src)):
                    target = dst if not src.endswith('/') else dst + f[len(src):]
                    break
            if target:
                moves[f] = target; continue
            name = posixpath.basename(f)
            if f not in KEEP_FROM_PROCESS and (PROCESS_DIRS.search('/' + f) or PROCESS_FILES.search(name)
                                               or (REVIEW_DIRS.search('/' + f) and not f.endswith('.md'))):
                removes.add(f); continue
            if f.endswith(TEXT_KEEP) or (f.endswith('.csv') and SMALL_TABLE_NAMES.search(name)):
                moves[f] = 'archive/sgrt_2026-10-18_21/' + f[len('research/'):]
            else:
                removes.add(f)
            continue
        raise SystemExit('unclassified: ' + f)
    return moves, removes


LINK = re.compile(r'(\]\()([^)\s]+)(\))')


def rewrite_links(old_path, new_path, text, moves, removed):
    def fix(m):
        target = m.group(2)
        if re.match(r'^[a-z]+:', target) or target.startswith('#'):
            return m.group(0)
        path, frag = (target.split('#', 1) + [''])[:2]
        if not path:
            return m.group(0)
        resolved = posixpath.normpath(posixpath.join(posixpath.dirname(old_path), path))
        trailing = path.endswith('/')
        if resolved in removed:
            return m.group(1) + ARCHIVE_NOTE + m.group(3)
        dest = moves.get(resolved)
        if dest is None:
            probe = resolved + '/'
            hits = [(s, d) for s, d in DIR_MOVES if probe.startswith(s)]
            if hits:
                s, d = max(hits, key=lambda x: len(x[0]))
                dest = (d + probe[len(s):]).rstrip('/')
        final = dest if dest is not None else resolved
        rel = posixpath.relpath(final.rstrip('/'), posixpath.dirname(new_path) or '.')
        if trailing and not rel.endswith('/'):
            rel += '/'
        return m.group(1) + rel + ('#' + frag if frag else '') + m.group(3)
    return LINK.sub(fix, text)


ARCHIVE_NOTE = '/archive/README.md#удалённые-материалы'
DIR_MOVES = []


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--apply', action='store_true')
    ap.add_argument('--out', default='.agent-ops')
    args = ap.parse_args()
    files = git_files()
    moves, removes = classify(files)
    global DIR_MOVES
    dirs = {}
    for s, d in moves.items():
        sd, dd = posixpath.dirname(s) + '/', posixpath.dirname(d) + '/'
        dirs.setdefault(sd, set()).add(dd)
    DIR_MOVES = sorted(((s, next(iter(d))) for s, d in dirs.items() if len(d) == 1), key=lambda x: -len(x[0]))
    os.makedirs(args.out, exist_ok=True)
    json.dump({'source_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip(),
               'moves': moves, 'removed': sorted(removes)},
              open(posixpath.join(args.out, 'plan.json'), 'w'), ensure_ascii=False, indent=1)
    open(posixpath.join(args.out, 'removed.txt'), 'w').write('\n'.join(sorted(removes)) + '\n')
    print(json.dumps({'files': len(files), 'moves': len(moves), 'removed': len(removes),
                      'kept_in_place': len(files) - len(moves) - len(removes)}))
    if not args.apply:
        return
    texts = {}
    for f in files:
        if f.endswith('.md') and f not in removes:
            texts[f] = open(f, encoding='utf-8', errors='surrogateescape').read()
    for chunk in range(0, len(removes), 500):
        subprocess.check_call(['git', 'rm', '-q', '--cached', '--'] + sorted(removes)[chunk:chunk + 500])
    for f in removes:
        if os.path.lexists(f):
            os.remove(f)
    for src, dst in sorted(moves.items()):
        os.makedirs(posixpath.dirname(dst), exist_ok=True)
        subprocess.check_call(['git', 'mv', '-k', src, dst])
    changed = 0
    for old, text in texts.items():
        new = moves.get(old, old)
        updated = rewrite_links(old, new, text, moves, removes)
        if updated != text:
            open(new, 'w', encoding='utf-8', errors='surrogateescape').write(updated)
            changed += 1
    prefixes = list(CURRENT_SGRT)
    for f in ['decisions.json'] + [p for p in files if p.startswith('references/') and p.endswith('.json')
                                   and p not in removes]:
        text = open(f, encoding='utf-8').read()
        updated = text
        for s, d in prefixes:
            updated = updated.replace(s, d)
        if updated != text:
            open(f, 'w', encoding='utf-8').write(updated)
            subprocess.check_call(['git', 'add', '-f', f])
            changed += 1
    for dirpath, dirnames, filenames in os.walk('.', topdown=False):
        if '.git' in dirpath:
            continue
        if not os.listdir(dirpath):
            os.rmdir(dirpath)
    subprocess.check_call(['git', 'add', '-A', '-f', '--'] + sorted(set(moves.values())))
    print(json.dumps({'links_rewritten_in_files': changed}))


if __name__ == '__main__':
    main()
