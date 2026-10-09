# Shatalovo-1 code-field clarification

The values in V34 described as source/native OKTMO (`66633495151` for Shatalovo-1 and `66633495101` for the village) are present in the raw 2021 parquet's field named `oktmo` and in the selected-observations layer as `source_native_id` / `oktmo`. They are not the values in the distinct raw field `oktmo_dadata`.

For Shatalovo-1, `oktmo_dadata=66533000327`; for the village, `oktmo_dadata=66533000316`. The raw rows also contain `okato_dadata=66233000229` and `66233000192`, respectively, plus distinct FIAS IDs. The crosscheck receipt's “OKTMO” values refer to the DaData provider field `oktmo_dadata`; the V34 source/native values refer to raw-source `oktmo`. Both pairs are retained under their correct field axes. V34 is not rewritten; its code statement is clarified here to avoid conflating the raw source-native field with the provider code field.

Neither code pair is treated as a temporal identifier or reason to merge the two current settlement rows. Existing point context remains source-specific: the two QID-bound representative points are distinct and about 62m apart; that proximity does not allocate or combine population.
