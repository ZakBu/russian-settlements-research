# Osinovsky selected-UID correction

This standalone v2 correction supersedes only the Marxovsky Osinovka 2021 endpoint in the prior Saratov/Tver handoff. The v1 packet remains unchanged.

The prior endpoint `...:parquet:117340` was incorrect: physical row117340 is the Osinovskoe municipal aggregate, not an additive settlement record. Canonical `selected_observations.parquet` contains row117341: `поселок Осиновский`, population894, direct published value, OKTMO63626453101, coordinates 51.5763684/46.8065347.

The corrected lineage is 2002 Осиновка → 2010 Осиновка → 2021 поселок Осиновский. The 2002 county heading, 2010 flanks, county-qualified 2009 classifier, and own article former-name statement support identity. Counts and quality labels remain native. Point use for earlier rows is retrospective only.
