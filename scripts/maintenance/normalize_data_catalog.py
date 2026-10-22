"""Classify source metadata and resolve only symlink targets present in the source snapshot."""
import posixpath


def normalize(catalog, special):
    assert special['source_commit'] == catalog['source_commit']
    rows = {row['path']: row for row in catalog['files']}
    classified = []
    for source in special['files']:
        row = rows[source['path']]
        original = catalog['objects'][source['original_blob']]
        assert original['bytes'] == source['original_bytes']
        assert original['sha256'] == source['original_sha256']
        original['source_kind'] = ('git_symlink_metadata' if source['original_git_mode'] == '120000'
                                   else 'appledouble_metadata')
        original['usable_as_table'] = False
        if 'parquet_schema_error' in original:
            original['format_inspection_note'] = original.pop('parquet_schema_error')
        row['source_provenance'] = dict(source)
        row['kind'] = source['kind']
        row['usable_as_table'] = source['kind'] == 'resolved_symlink_data'
        if row['usable_as_table']:
            target_path = posixpath.normpath(posixpath.join(posixpath.dirname(row['path']), source['link_target']))
            assert target_path == source['resolved_target_path']
            assert target_path in rows and rows[target_path]['blob'] == source['resolved_blob']
            target = catalog['objects'][source['resolved_blob']]
            assert target.get('schema_id') and target.get('sha256')
            row.update(blob=source['resolved_blob'], bytes=target['bytes'], asset=target['asset'],
                       materialization='independent_copy_of_resolved_target')
            paths = target.setdefault('additional_materialization_paths', [])
            if row['path'] not in paths:
                paths.append(row['path'])
        else:
            assert row['blob'] == source['original_blob']
            row['materialization'] = 'original_metadata_bytes_as_regular_file'
        classified.append({'path': row['path'], 'kind': row['kind'],
                           'source_blob': source['original_blob'],
                           'usable_as_table': row['usable_as_table'],
                           'inspection_note': original.get('format_inspection_note'),
                           'resolved_target_path': source.get('resolved_target_path')})
    errors = {sha: obj['parquet_schema_error'] for sha, obj in catalog['objects'].items()
              if 'parquet_schema_error' in obj}
    catalog['counts']['source_logical_bytes'] = catalog['counts']['logical_bytes']
    catalog['counts']['materialized_logical_bytes'] = sum(row['bytes'] for row in catalog['files'])
    catalog['counts']['parquet_schema_errors'] = len(errors)
    catalog['readability'] = {
        'core_parquet_schema_errors': {sha: err for sha, err in errors.items()
                                       if 'core' in catalog['objects'][sha]['profiles']},
        'historical_parquet_schema_errors': errors,
        'classified_non_table_source_objects': classified,
        'unavailable_historical_link_targets': [r['resolved_target_path'] for r in classified
                                                if r['kind'] == 'unresolved_symlink_metadata'],
        'note': 'ZIP objects preserve original bytes. Two resolvable symlink paths materialize copies of their target tables. Two broken source links remain explicit metadata; their absent targets have not been recovered. AppleDouble is metadata. Source and materialized byte totals are separate.'}
    return catalog
