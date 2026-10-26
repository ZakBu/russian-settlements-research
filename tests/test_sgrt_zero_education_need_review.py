"""Meaningful controls for supplementary activity mislabelled as a school."""
import json
import unittest
import pandas as pd
from scripts.sgrt_zero.education_need_review import review_education_need_scope, _general_signal


def row(name, tags=None, **extra):
    return dict(name=name, tags_json=json.dumps(tags or {},ensure_ascii=False),
        service_code='school_general',eligible=True,supply_status='observed',
        source_record_id='np-a',site_lat=53.,site_lon=40.,**extra)


class EducationNeedReviewTests(unittest.TestCase):
    def test_explicit_actual_wrong_roles_are_held_and_raw_claims_survive(self):
        names=['KIBERone','Центр развития творчества детей и юношества',
            'ФГБОУ ВПО "Брянская государственная сельскохозяйственная академия"',
            'д/с Калинка(новое здание)','МБДОУ №13','МДОБУ №15 Дружные ребята',
            'Кабинет вводных инструктажей','ГАУ "МФЦ Усть-Кутского МР ИО"',
            'Социальный участковый','Лыжный стадион','Объект Здравоохранения',
            'Бывший сестринский корпус','Mockingbird Social English club',
            'Школа №309 (детский сад)','ПТУ №13','СПТУ65','Профессиональный лицей №4',
            'Профлицей №2','Медресе','Школа раннего развития']
        source=pd.DataFrame([row(name) for name in names]);result=review_education_need_scope(source)
        self.assertFalse(result.route_eligible.any())
        self.assertTrue(result.source_education_need_review_reason.ne('').all())
        pd.testing.assert_frame_equal(source,result[source.columns])

    def test_actual_general_school_negative_controls_are_retained(self):
        source=pd.DataFrame([row('TOP IT SCHOOL',{'website':'https://topitschool.ru/chelyabinsk'}),
            row('Центр интеллектуального развития «СМАРТ»',{'website':'https://smart-cid.ru'}),
            row('Частная школа «Потенциал»'),row('MBA Montessori School'),
            row('English International School'),row('Академия Наяновой'),
            row('Центр духовного развития молодежи'),
            row('Средняя общеобразовательная школа №1',{'description':'Проводятся кружки робототехники'}),
            row('СОШ №2',{'operator':'KIBERone','website':'https://kiber-one.com'})])
        result=review_education_need_scope(source)
        self.assertTrue(result.route_eligible.all())
        self.assertFalse(result.source_education_need_review_reason.ne('').any())

    def test_combined_primary_school_nursery_is_not_nursery_only(self):
        source=pd.DataFrame([row('НШ-ДС "Аркаим"'),row('НШДС с.Кальма'),row('НОШ-Детский Сад с.Гагшор'),
            row('Начальная школа - детский сад №2'),row('Школа-сад №84 «Лингвист»'),
            row('МБДОУ «Палкинская средняя общеобразовательная школа»'),
            row('Школа и детский сад'),row('Детский сад, школа'),
            row('Лицей-детский сад'),row('Частная школа и детский сад Интеллект-плюс'),
            row('Кушьинская СОШ, д/с'),row('МОБУ СОШ, Детский сад с.Орехово'),
            row('Короткое имя',{'official_name':'Частное общеобразовательное учреждение «Средняя общеобразовательная школа - детский сад»'}),
            row(None,{'official_name':'Менделеевская начальная школа – детский сад'}),
            row('Детский сад №36',{'official_name':'Государственное бюджетное общеобразовательное учреждение начальная школа - детский сад №36'})])
        self.assertTrue(review_education_need_scope(source).route_eligible.all())

    def test_explicit_general_programme_signal_prevents_brand_inference(self):
        source=pd.DataFrame([row('Средняя общеобразовательная школа KIBERone'),
            row('KIBERone',{'education_profile:general':'yes'}),row('Медресе',{'education_profile:general':'yes'}),
            row('Профессиональный лицей',general_school_programme_verified=True)])
        result=review_education_need_scope(source)
        self.assertTrue(result.route_eligible.all())
        self.assertTrue(result.source_education_need_review_conflicting_general_signal.all())

    def test_ISCED3_does_not_prove_general_programme_at_a_vocational_school(self):
        checked=review_education_need_scope(pd.DataFrame([row('ПТУ №1',{'isced:level':'3'})]))
        self.assertFalse(checked.route_eligible.iloc[0])
        self.assertIn('vocational',checked.source_education_need_review_reason.iloc[0])

    def test_numeric_stages_do_not_turn_a_nursery_into_a_general_school(self):
        checked=review_education_need_scope(pd.DataFrame([row('МБДОУ №1',{'isced:level':'1','grades':'1-4'})]))
        self.assertFalse(checked.route_eligible.iloc[0])
        self.assertIn('preschool',checked.source_education_need_review_reason.iloc[0])

    def test_supplementary_general_education_programmes_are_not_basic_school_programmes(self):
        self.assertFalse(_general_signal('центр дополнительных общеобразовательных программ',{},{}))
        self.assertTrue(_general_signal('общеобразовательная школа',{},{}))
        source=pd.DataFrame([row('МБУ ДО Центр дополнительных общеобразовательных программ'),
            row('СОШ, отделение дополнительного образования')])
        checked=review_education_need_scope(source)
        self.assertEqual(checked.route_eligible.tolist(),[False,True])

    def test_operator_partner_and_general_school_robotics_are_not_own_roles(self):
        source=pd.DataFrame([row('Школа №1',{'operator':'KIBERone',
            'description':'Партнерская школа программирования проводит кружки робототехники'}),
            row('Потенциал',{'operator':'МБУ ДО Центр творчества'}),
            row('ООШ №8',{'description':'Школа программирования и общеобразовательная программа'})])
        self.assertTrue(review_education_need_scope(source).route_eligible.all())

    def test_own_robocode_description_is_held_without_inferring_grades_from_ages(self):
        source=pd.DataFrame([row('Robo code',{'description':'школа программирования'}),
            row('KIBERone',{'description':'Обучаем детей 6-14 лет'}),
            row('KIBERone',{'grades':'4-17'})])
        self.assertFalse(review_education_need_scope(source).route_eligible.any())

    def test_previous_false_and_unknown_holds_are_never_reactivated(self):
        source=pd.DataFrame([row('Обычная школа',route_eligible=False),
            row('TOP IT SCHOOL',route_eligible=None),row('Гимназия',route_eligible='false')])
        self.assertFalse(review_education_need_scope(source).route_eligible.any())

    def test_other_services_and_source_ineligible_records_are_not_reclassified(self):
        source=pd.DataFrame([dict(row('KIBERone'),service_code='vocational_education'),
            dict(row('МФЦ'),eligible=False),dict(row('ПТУ №5'),supply_status='held_old_scope')])
        result=review_education_need_scope(source)
        self.assertTrue(result.route_eligible.all())
        pd.testing.assert_frame_equal(source,result[source.columns])

    def test_reviewed_language_centre_requires_both_own_name_and_own_site(self):
        source=pd.DataFrame([row('Лингва',{'website':'http://www.rub-lingvo.ru/'}),
            row('Лингва'),row('Потенциал',{'website':'http://www.rub-lingvo.ru/'}),
            row('Средняя общеобразовательная школа «Лингва»',{'website':'http://www.rub-lingvo.ru/'})])
        checked=review_education_need_scope(source)
        self.assertEqual(checked.route_eligible.tolist(),[False,True,True,True])

    def test_malformed_website_does_not_reclassify_a_generic_name_or_crash(self):
        checked=review_education_need_scope(pd.DataFrame([row('Лингва',{'website':'https://[broken'})]))
        self.assertTrue(checked.route_eligible.iloc[0])


if __name__=='__main__':
    unittest.main()
