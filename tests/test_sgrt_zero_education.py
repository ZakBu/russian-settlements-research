import sys
from pathlib import Path
import unittest

import pandas as pd

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts.sgrt_zero.education import build_sites, np_offers, school_orders, parse_literal_levels, regional_coverage, FEDERAL_CITY_IDS, non_general_school_reason, school_need_scope, semantic_education_text, semantic_programme_tags, instructional_site_role


def reference():
    return pd.DataFrame({'root':['root-a','root-b','root-m'],
        'source_record_id':['a','b','m'],'name':['А','Б','Москва'],
        'region':['вологодская','вологодская','москва'],
        'population_role':['ordinary_settlement_record','ordinary_settlement_record','external_context_nonadditive'],
        'ordinary_spatial_2021':[True,True,False],
        'lat':[59.,59.1,55.75],'lon':[39.,39.1,37.62]})


def legacy():
    r=reference();return pd.DataFrame({'id':['old-a','old-b','old-m'],'root':r.root,
        'source_record_id_2021':r.source_record_id,'name':r.name,'region':r.region,'lat':r.lat,'lon':r.lon})


def objects(**changes):
    d={'site_id':'osm:node:1','education_group':'school','source_snapshot':'2026-10-19T20:21:11Z',
       'lat':59.,'lon':39.,'tags_json':'{"amenity":"school"}',
       'baseline_uid':'old-a','candidate_uid':None,'source_address_locality':'А',
       'source_address_state':None,'link_status':'explicit_address_locality_unique_within5km',
       'possible_duplicate_of':None,'source_start_date':None,'source_end_date':None,'name':'Средняя школа №11'}
    d.update(changes);return pd.DataFrame([d])


def official():
    return pd.DataFrame([{'provider_id':'official:'+s,'source_record_id':s,'service_code':'preschool_official',
        'source_id':'ROSSTAT_NP2025_PRIMARY_BOOKS','observation_year':2025,'supply_status':'observed',
        'known_positive_source_rows':1,'capacity_total':100.,'capacity_unit':'total_preschool_places_not_vacant_places'} for s in ['a','b']])


class ZeroEducationTest(unittest.TestCase):
    def test_mixed_script_semantics_preserves_raw_addresses_and_general_art_schools(self):
        raw='Детская школа искусcтв №3'
        d=build_sites(objects(name=raw,tags_json='{"amenity":"school","addr:city":"А"}'),reference(),legacy())
        self.assertFalse(d.eligible.iloc[0])
        self.assertEqual(d['name'].iloc[0],raw)
        self.assertEqual(d.education_semantic_name.iloc[0],'Детская школа искусств №3')
        self.assertEqual(d.source_record_id.iloc[0],'a')
        self.assertEqual(d.source_address_locality.iloc[0],'А')
        self.assertIn('"addr:city":"А"',d.tags_json.iloc[0])
        for name in ['Общеобразовательная школа искусcтв','Гимназия искусств',
                     'Средняя школа с углубленным изучением английского языка','English International School']:
            self.assertTrue(build_sites(objects(name=name),reference(),legacy()).eligible.iloc[0])
        self.assertEqual(semantic_education_text('English International School'),'English International School')
        self.assertEqual(semantic_education_text('ProЛицей'),'ProЛицей')
        view=semantic_programme_tags('{"school:type":"musіc","addr:city":"Cело"}')
        self.assertEqual(view['school:type'],'music')
        self.assertEqual(view['addr:city'],'Cело')

    def test_residential_or_support_unit_does_not_inherit_institution_programme(self):
        for family,name in [('university','Общежитие ВятГУ №2'),('college','Общежитие техникума'),
                            ('school','Общежитие интернат'),('preschool','Общежитие'),
                            ('university','Котельная университета'),('college','Столовая колледжа')]:
            with self.subTest(family=family,name=name):
                d=build_sites(objects(education_group=family,name=name),reference(),legacy())
                self.assertFalse(d.eligible.iloc[0])
                self.assertFalse(d.instructional_site_role_eligible.iloc[0])
                self.assertEqual(d.education_group_original.iloc[0],family)
        generic=build_sites(objects(education_group='college',name='ПТУ №55',
            tags_json='{"amenity":"college","building":"dormitory"}'),reference(),legacy())
        self.assertFalse(generic.eligible.iloc[0])
        self.assertEqual(generic.instructional_site_role.iloc[0],'residential_building_form_teaching_unresolved')

    def test_teaching_campus_boarding_school_and_current_reuse_remain_valid(self):
        cases=[('school','Общеобразовательная школа-интернат №15','{"amenity":"school","building":"school"}'),
               ('school','Индигская школа - столовая и Интернат','{"amenity":"school"}'),
               ('school','Школа, спортзал','{"amenity":"school"}'),
               ('school','Общеобразовательная школа-интернат с общежитием','{"amenity":"school"}'),
               ('university','Учебно-научный кампус университета','{"amenity":"university"}'),
               ('university','Учебный корпус №2','{"amenity":"university","building":"dormitory","building:use":"education"}'),
               ('university','Учебный корпус (бывшее общежитие)','{"amenity":"university","building":"dormitory"}'),
               ('college','Учебно-лабораторный корпус колледжа','{"amenity":"college"}')]
        for family,name,tags in cases:
            with self.subTest(family=family,name=name):
                self.assertTrue(build_sites(objects(education_group=family,name=name,tags_json=tags),reference(),legacy()).eligible.iloc[0])
        separate=build_sites(objects(name='Школа №5, общежитие',tags_json='{"amenity":"school"}'),reference(),legacy())
        self.assertFalse(separate.eligible.iloc[0])

    def test_source_operation_conflict_is_retained_without_proving_actual_closure(self):
        for changes in [dict(name='Бывшая школа'),dict(name='Школа (закрыта)'),
                        dict(tags_json='{"amenity":"school","abandoned:building":"yes"}'),
                        dict(tags_json='{"amenity":"school","building":"construction"}')]:
            d=build_sites(objects(**changes),reference(),legacy())
            self.assertFalse(d.eligible.iloc[0])
            self.assertEqual(d.service_code.iloc[0],'school_general')
            self.assertTrue(bool(d.source_operational_conflict.iloc[0]))
            self.assertEqual(d.supply_status.iloc[0],'held_source_operational_conflict_not_actual_closure_proof')
        private=build_sites(objects(tags_json='{"amenity":"school","operator:type":"private","access":"private"}'),reference(),legacy())
        self.assertTrue(private.eligible.iloc[0])
        self.assertFalse(private.education_admission_conditions_verified.iloc[0])
        self.assertEqual(private.source_education_access_literal.iloc[0],'private')

    def test_programme_scope_is_checked_across_all_education_families(self):
        held=[('university','Детская школа искусств'),('college','Детская школа искусств №6'),
              ('college','Детский сад №16'),('college','Копейская автошкола ДОСААФ'),
              ('school','Администрация сельсовета'),('school','Плосковский сельский дом культуры'),
              ('school','Институт повышения квалификации'),('school','Зооветтехникум'),
              ('preschool','Детская музыкальная школа'),('school','Детский санаторий МВД'),
              ('school','Детский дом'),('school','Пионерский лагерь'),
              ('school','Физкультурно-оздоровительный комплекс')]
        held.extend([('preschool','Управление образования Администрации Тында'),
                     ('preschool','ОМС Управление образованием'),
                     ('school','Социально-реабилитационный центр Восточный')])
        for group,name in held:
            with self.subTest(group=group,name=name):
                d=build_sites(objects(education_group=group,name=name),reference(),legacy())
                self.assertFalse(d.eligible.iloc[0])
                self.assertEqual(d.education_group_original.iloc[0],group)
        valid=[('preschool','Школа №1450'),('preschool','Школа №3. Дошкольное отделение'),
               ('college','Профессионально-технический лицей №6'),('college','Музыкальное училище'),
               ('college','Колледж искусств'),('university','Университет искусств'),
               ('university','Школа образования ТюмГУ'),('university','Высшая школа экономики'),
               ('college','Московская театральная школа Олега Табакова'),
               ('school','Университетская школа Елабужского института')]
        for group,name in valid:
            with self.subTest(group=group,name=name):
                self.assertTrue(build_sites(objects(education_group=group,name=name),reference(),legacy()).eligible.iloc[0])

    def test_continuing_training_does_not_establish_vocational_or_university_degree(self):
        for group in ['college','university']:
            d=build_sites(objects(education_group=group,name='Институт повышения квалификации и профессиональной переподготовки'),reference(),legacy())
            self.assertFalse(d.eligible.iloc[0])
            self.assertEqual(d.education_need_scope.iloc[0],'continuing_or_employer_training_degree_not_established')
            self.assertEqual(d.service_code.iloc[0],{'college':'vocational_education','university':'higher_education'}[group])

    def test_preschool_specific_contingent_is_not_universal_daycare(self):
        for name in ['Детский сад компенсирующего вида','Специальный коррекционный детсад',
                     'ДС для детей с тяжелыми нарушениями речи','Санаторный детсад',
                     'Детский сад для детей-сирот']:
            with self.subTest(name=name):
                d=build_sites(objects(education_group='preschool',name=name),reference(),legacy())
                self.assertEqual(d.service_code.iloc[0],'preschool')
                self.assertFalse(d.eligible.iloc[0])
                self.assertEqual(d.education_need_scope.iloc[0],'dedicated_preschool_contingent_not_universal')
        for name in ['Детсад №11 (Логопедический)','Детский дом-школа']:
            self.assertEqual(school_need_scope('preschool',name,'{}'),'dedicated_preschool_contingent_not_universal')
        for name in ['Детский сад комбинированного вида','Инклюзивный детский сад',
                     'Детский сад Логопедиум','Логопедiя']:
            self.assertTrue(build_sites(objects(education_group='preschool',name=name),reference(),legacy()).eligible.iloc[0])

    def test_supplementary_training_arts_and_ancillary_sites_are_not_general_schools(self):
        names=['Детская Школа Искуств (ДШИ)','МБОУ ДОДДШИ ПГП','ДМШ №3','ДХШ',
            'Музыкльная школа','Детская школа хореографии Соцветие','ДЮШС №96 Борец',
            'Спортшкола','Школа олимпийского резерва','Детская теннисная академия',
            'Футбольная школа ФК Краснодар','Дом детского творчества','ЦДТ Восход',
            'Школа РОСТО','ДОСААФ России','Межшкольный учебный комбинат',
            'НОЧУ Учебный центр Медрл Плюс','Motive — Школа мастеров красоты',
            'Школа № 887. Отделение дополнительного образования детей',
            'Лицей № 111. Корпус дошкольного образования','СОШ №10 (дошкольное отделение)',
            'Дошкольное учебное заведение Ясли-сад Звездочка','Управление образования',
            'Спортзал школы №5','Лингвистический центр Маленький принц',
            'Детский издательский центр Соломбальского Дома детского творчества',
            'Училище олимпийского резерва','Обучение виндсерфу',
            'УЦ Судоводитель','Репетитор','Восточные танцы','Академия хореографии']
        for name in names:
            with self.subTest(name=name):
                self.assertTrue(non_general_school_reason('school',name,'{"amenity":"school"}'))

    def test_subject_focus_person_name_and_adapted_curriculum_do_not_remove_general_school(self):
        names=['Средняя общеобразовательная школа с художественным уклоном',
            'Средняя музыкальная общеобразовательная школа','Гимназия (английская) №17',
            'Лингвистический лицей №22','Школа с углубленным изучением английского языка',
            'Каратабанская СОШ','Дюллюкинская СОШ','Подшиваловская средняя школа',
            'Средняя школа им. С. И. Ростоцкого','Школа имени Чайковского',
            'Школа №1450 Олимп','Школа №8 «Музыка»','Школа индивидуального обучения Шанс',
            'Школа надомного обучения №388','Школа-интернат для слабослышаших детей',
            'Немецкая школа при Генконсульстве Германии','Специализированный учебно-научный центр УрФУ',
            'Лингва','IT School','Английская школа']
        for name in names:
            with self.subTest(name=name):
                self.assertFalse(non_general_school_reason('school',name,'{"amenity":"school"}'))
        self.assertFalse(non_general_school_reason('school','Средняя общеобразовательная музыкальная школа',
            '{"school:type":"music","isced:level":"1;2;3"}'))

    def test_specific_non_general_tags_and_mixed_institution_scopes_remain_explicit(self):
        for tag in ['"education":"facultative_school"','"education":"courses"',
            '"school":"diving"','"school":"optional"','"school":"vocational"',
            '"training":"driving"','"isced:level":"0"']:
            with self.subTest(tag=tag):
                self.assertTrue(non_general_school_reason('school','Название','{'+tag+'}'))
        for tag in ['"school":"blind"','"school":"special_education_needs"']:
            self.assertFalse(non_general_school_reason('school','Школа','{'+tag+'}'))
        mixed=non_general_school_reason('school','МБОУ Гимназия МБДО ДОД ДМШ','{}')
        self.assertIn('conflicting',mixed)
        d=build_sites(objects(name='Детская Школа Искуств (ДШИ)'),reference(),legacy())
        self.assertEqual(len(d),1)
        self.assertFalse(d.eligible.iloc[0])
        self.assertTrue(pd.isna(d.service_code.iloc[0]))
        self.assertEqual(d.education_group_original.iloc[0],'school')

    def test_need_specific_general_curriculum_retained_without_universal_daily_admission(self):
        for name in ['Вечерняя школа №10','Вечерняя (сменная) общеобразовательная школа',
                     'Общеобразовательная школа для взрослых','Коррекционная школа №5',
                     'Школа-интернат для слабослышащих детей',
                     'Специальная общеобразовательная школа закрытого типа',
                     'Вечерняя сменная общеобразовательная школа №1','Открытая (сменная) школа',
                     'Школа для детей с ОВЗ','ШИ ОВЗ','Интернат глухонемых',
                     'Школа для слепоглухих детей','Школа для умственно осталых детей',
                     'Школа умственно отсталых','Дербетовский дом-интернат для умственно-осталых детей',
                     'Школа для детей, воспитанников с ограниченными возможностями здоровья',
                     'Школа для обучающихся c ограниченными возможностями здоровья',
                     'Начальная школа-детсад коррекции зрения',
                     'Центр психолого-педагогической реабилитации и коррекции Восточный',
                     'Специальное учебно-воспитательное учреждение №14 Подросток']:
            with self.subTest(name=name):
                d=build_sites(objects(name=name,source_isced_level='1;2;3'),reference(),legacy())
                self.assertEqual(d.service_code.iloc[0],'school_general')
                self.assertFalse(d.eligible.iloc[0])
                self.assertEqual(d.supply_status.iloc[0],'held_need_specific_general_curriculum_not_default_daytime')
                self.assertTrue(d.grades_known.iloc[0])
                self.assertFalse(school_orders(d).eligible.any())
        for name in ['Обычная школа-интернат','Инклюзивная общеобразовательная школа',
                     'Школа №7 (Центр адаптированного обучения)','СОШ имени П.А. Слепцова']:
            self.assertEqual(school_need_scope('school',name,'{}'),
                             'general_daytime_school_proxy_admission_not_verified')
        self.assertEqual(school_need_scope('school','Инклюзивная общеобразовательная школа для детей с ОВЗ','{}'),
                         'general_daytime_school_proxy_admission_not_verified')
        d=build_sites(objects(tags_json='{"amenity":"school","school":"blind"}'),reference(),legacy())
        self.assertEqual(d.service_code.iloc[0],'school_general')
        self.assertFalse(d.eligible.iloc[0])

    def test_coded_special_school_type_is_not_an_ordinary_school_number(self):
        for name in ['Школа Интернат II-вида','Школа-интернат VIII вида',
                     'Школа-интернат спец.корр. 5-го вида','Школа VIII вида №1',
                     'Школа-интернат №5 спец.корр. 8ого вида']:
            d=build_sites(objects(name=name),reference(),legacy())
            self.assertFalse(d.eligible.iloc[0])
            self.assertEqual(d.service_code.iloc[0],'school_general')
            self.assertEqual(d.education_need_scope.iloc[0],'dedicated_special_needs_general_curriculum_not_universal')
        for name in ['Школа-интернат №8','Школа-интернат II ступени','Школа-интернат №2']:
            self.assertTrue(build_sites(objects(name=name),reference(),legacy()).eligible.iloc[0])

    def test_explicit_general_isced_can_disambiguate_college_legal_name(self):
        self.assertFalse(non_general_school_reason('school','Балтика-колледж имени маршала Говорова',
                                                  '{"amenity":"school","isced:level":"1;2;3"}'))

    def test_literal_identity_is_separate_from_nearest_geometry(self):
        a=build_sites(objects(),reference(),legacy())
        self.assertEqual(a.source_record_id.iloc[0],'a')
        b=build_sites(objects(link_status='spatial_candidate_within2_5km_separated_not_identity_proof',baseline_uid=None,candidate_uid='old-a'),reference(),legacy())
        self.assertIsNone(b.source_record_id.iloc[0])
        self.assertTrue(b.eligible.iloc[0])
        self.assertEqual(b.nearest_reference_source_record_id.iloc[0],'a')
        self.assertFalse(b.nearest_reference_is_identity.iloc[0])

    def test_explicit_status_alone_does_not_override_name_conflict_or_empty_name(self):
        for name in ['Б',None,'']:
            d=build_sites(objects(source_address_locality=name),reference(),legacy())
            self.assertIsNone(d.source_record_id.iloc[0])

    def test_source_year_is_read_from_snapshot(self):
        new=build_sites(objects(),reference(),legacy())
        old=build_sites(objects(source_snapshot='2021-01-01'),reference(),legacy())
        self.assertEqual(new.observation_year.iloc[0],2026)
        self.assertEqual(old.observation_year.iloc[0],2021)
        self.assertNotEqual(new.source_id.iloc[0],old.source_id.iloc[0])

    def test_inactive_and_proven_date_conflicts_are_excluded(self):
        for change in [{'tags_json':'{"amenity":"school","abandoned":"yes"}'},
                       {'tags_json':'{"amenity":"school","disused:amenity":"school"}'},
                       {'source_end_date':'2016'},{'source_start_date':'2027'}]:
            d=build_sites(objects(**change),reference(),legacy())
            self.assertFalse(d.eligible.iloc[0])
            self.assertNotEqual(d.supply_status.iloc[0],'observed')
        uncertain=build_sites(objects(source_end_date='2026'),reference(),legacy())
        self.assertTrue(uncertain.eligible.iloc[0])

    def test_specialized_duplicate_and_invalid_geometry_retained_but_excluded(self):
        for change in [{'education_group':'specialized_non_general_school','name':'Детская музыкальная школа'},
                       {'possible_duplicate_of':'osm:way:2'},{'lat':95.}]:
            d=build_sites(objects(**change),reference(),legacy())
            self.assertEqual(len(d),1)
            self.assertFalse(d.eligible.iloc[0])

    def test_explicit_comprehensive_arts_school_can_correct_upstream_specific_group(self):
        for name in ['Средняя общеобразовательная школа №36 с углублённым изучением иностранных языков',
                     'Художественно-эстетический лицей №98',
                     'Общеобразовательная православная школа искусств','Гимназия восточных языков №4']:
            d=build_sites(objects(education_group='specialized_non_general_school',name=name),reference(),legacy())
            self.assertTrue(d.eligible.iloc[0])
            self.assertEqual(d.service_code.iloc[0],'school_general')
            self.assertEqual(d.education_group_original.iloc[0],'specialized_non_general_school')
        d=build_sites(objects(education_group='specialized_non_general_school',name='МОУ Гимназия №1 (музыкальное отделение)'),reference(),legacy())
        self.assertFalse(d.eligible.iloc[0])

    def test_school_name_never_creates_grade_evidence(self):
        d=build_sites(objects(name='Средняя школа №11'),reference(),legacy())
        self.assertTrue(school_orders(d).empty)
        self.assertFalse(d.grade_inferred_from_name_or_population.iloc[0])

    def test_explicit_isced_does_not_imply_lower_levels(self):
        d=build_sites(objects(source_isced_level='3'),reference(),legacy())
        a=school_orders(d)
        self.assertEqual(a.service_code.tolist(),['school_upper_secondary'])
        self.assertFalse(a.complete_stage_offering_established.any())
        d=build_sites(objects(source_grades='5-11'),reference(),legacy())
        self.assertEqual(set(school_orders(d).service_code),{'school_lower_secondary','school_upper_secondary'})
        self.assertEqual(parse_literal_levels('11-1',1,12),[])
        self.assertEqual(parse_literal_levels('1;2;3'),[1,2,3])

    def test_official_centroid_not_added_on_top_of_own_strict_osm_site(self):
        sites=build_sites(objects(education_group='preschool'),reference(),legacy())
        d=np_offers(sites,official(),reference())
        own=d[d.source_pool.eq('osm_strict_np_presence')]
        self.assertFalse(own.default_external_seed_eligible.any())
        obs=d[d.source_pool.eq('official_preschool_np2025')].set_index('source_record_id')
        self.assertFalse(obs.loc['a','default_external_seed_eligible'])
        self.assertTrue(obs.loc['b','default_external_seed_eligible'])
        self.assertTrue(d.np_offer_rows_are_not_institution_counts.all())

    def test_unknown_site_does_not_cancel_official_np_presence(self):
        sites=build_sites(objects(education_group='preschool',link_status='unresolved_no_locality_identity',baseline_uid=None),reference(),legacy())
        d=np_offers(sites,official(),reference())
        self.assertTrue(d.default_external_seed_eligible.all())
        self.assertFalse(d.capacity_is_vacant_places.any())

    def test_federal_context_with_zero_ordinary_denominator_is_unknown_fraction(self):
        sites=build_sites(objects(lat=55.75,lon=37.62,baseline_uid='old-m',source_address_locality='Москва'),reference(),legacy())
        offers=np_offers(sites,official(),reference())
        c=regional_coverage(sites,offers,reference())
        m=c[c.region.eq('москва')]
        self.assertTrue(m.np_known_offer_fraction.isna().all())
        self.assertEqual(int(m.eligible_source_sites.sum()),1)

    def test_repeated_physical_identity_is_not_silently_replicated(self):
        a=objects()
        with self.assertRaisesRegex(ValueError,'Repeated OSM'):
            build_sites(pd.concat([a,a]),reference(),legacy())

    def test_explicit_non_general_school_profile_excluded_without_overriding_general_name(self):
        for name in ['Детская музыкальная школа №4','Школа английского языка','Автошкола']:
            d=build_sites(objects(name=name),reference(),legacy())
            self.assertFalse(d.eligible.iloc[0])
            self.assertTrue(bool(d.non_general_school_reason.iloc[0]))
        normal=build_sites(objects(name='Средняя общеобразовательная школа с углубленным изучением английского языка'),reference(),legacy())
        self.assertTrue(normal.eligible.iloc[0])
        tagged=build_sites(objects(tags_json='{"amenity":"school","school:type":"music"}'),reference(),legacy())
        self.assertFalse(tagged.eligible.iloc[0])

    def test_literal_known_region_conflict_holds_legacy_identity(self):
        d=build_sites(objects(source_address_state='Москва'),reference(),legacy())
        self.assertIsNone(d.source_record_id.iloc[0])
        self.assertTrue(d.literal_region_conflicts_with_legacy_identity.iloc[0])
        self.assertTrue(d.eligible.iloc[0])

    def test_federal_city_literal_address_preserves_context_role_without_nearest_identity(self):
        ref=reference();sid=FEDERAL_CITY_IDS['москва']
        ref.loc[ref.source_record_id.eq('m'),'source_record_id']=sid
        leg=legacy();leg.loc[leg.source_record_id_2021.eq('m'),'source_record_id_2021']=sid
        changes=dict(lat=55.9,lon=37.7,baseline_uid=None,link_status='unresolved_no_locality_identity',
            source_address_locality='Москва',tags_json='{"amenity":"school","addr:city":"Москва"}')
        d=build_sites(objects(**changes),ref,leg)
        self.assertEqual(d.source_record_id.iloc[0],sid)
        self.assertEqual(d.population_role.iloc[0],'external_context_nonadditive')
        self.assertFalse(d.nearest_reference_is_identity.iloc[0])
        bad=build_sites(objects(**changes,source_address_state='Вологодская область'),ref,leg)
        self.assertIsNone(bad.source_record_id.iloc[0])

    def test_derived_city_coordinate_fills_geography_only_not_identity_or_census(self):
        ref=reference();ref.loc[ref.source_record_id.eq('m'),['lat','lon']]=float('nan')
        ctx=pd.DataFrame({'source_record_id':['m'],'lat':[55.75],'lon':[37.62]})
        d=build_sites(objects(lat=55.75,lon=37.62,baseline_uid=None,source_address_locality=None,
            link_status='unresolved_no_locality_identity'),ref,legacy(),ctx)
        self.assertIsNone(d.source_record_id.iloc[0])
        self.assertEqual(d.region.iloc[0],'москва')
        self.assertTrue(d.region_is_proxy.iloc[0])
        self.assertTrue(d.nearest_reference_uses_derived_city_coordinate.iloc[0])
        self.assertTrue(ref.loc[ref.source_record_id.eq('m'),'lat'].isna().all())


if __name__=='__main__':
    unittest.main()
