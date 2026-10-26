"""Meaningful controls for wrong grocery roles and retained mixed shops."""
from pathlib import Path
import sys
import unittest
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.sgrt_zero.retail_need_review import review_retail_need_scope


class RetailNeedReviewTests(unittest.TestCase):
    def frame(self, names, **fields):
        return pd.DataFrame({'source_name': names, 'service_code': 'daily_grocery',
            'supply_status': 'observed', 'eligible': True, 'route_eligible': True, **fields})

    def test_own_explicit_nonfood_categories_are_not_general_grocery(self):
        names=['Стройматериалы', 'Строительные и отделочные материалы',
               'Мебельный салон "Статус"', 'Сантехника', 'Бытовая химия и одежда',
               'Одежда и обувь', 'АВТОТРАКТОРОЗАПЧАСТИ', 'Канцелярские товары, зоотовары',
               'Хозтовары', 'Стройбаза "Татаев"','Промтовары','Аптека','Автомагазин Находка',
               'Табак и Ко','Электротовары','Мебельный магазин']
        result=review_retail_need_scope(self.frame(names))
        self.assertFalse(result.route_eligible.any())
        self.assertTrue(result.retail_need_scope_review_reason.ne('').all())

    def test_cosmetic_format_is_distinct_from_food_magnit(self):
        names=['Магнит косметик', 'Магнит-Косметик', 'М.Косметик',
               'Магнит', 'Магнит Семейный', 'Магазин "Магнит", "Магнит-Косметик"']
        result=review_retail_need_scope(self.frame(names))
        self.assertEqual(result.route_eligible.tolist(), [False,False,False,True,True,True])

    def test_mixed_food_and_household_shops_are_retained(self):
        names=['Еда, галантерея, обувь', 'Продукты, хозтовары', 'прод/хозтовары',
               'Хозпродтовары', 'Бакалея и бытовая химия', 'магазин автозапчасти и продуктовый',
               'Продмаг №7 РАЙПО, Промтовары №2','Продукты и табак']
        self.assertTrue(review_retail_need_scope(self.frame(names)).route_eligible.all())

    def test_marketing_supermarket_or_universam_does_not_prove_food(self):
        names=['Супермаркет стройматериалов','Мебельный универсам','Супермаркет Магнит Косметик',
               'Супермаркет','Универсам','Продукты, стройматериалы']
        self.assertEqual(review_retail_need_scope(self.frame(names)).route_eligible.tolist(),
                         [False,False,False,True,True,True])

    def test_pet_products_do_not_establish_human_grocery_supply(self):
        names=['Зоотовары, продукты для животных','Зоотовары, еда для кошек',
               'Зоотовары, продукты для людей','Продукты и корма для животных']
        self.assertEqual(review_retail_need_scope(self.frame(names)).route_eligible.tolist(),
                         [False,False,True,True])

    def test_operator_brand_and_unanchored_landmark_do_not_replace_own_role(self):
        frame=self.frame(['Сельский магазин', 'Ромашка','Берёзка'], tags_json=[
            '{"operator":"Магнит Косметик"}',
            '{"description":"Напротив магазина мебели"}',
            '{"description":"Магазин напротив магазина мебели"}'])
        self.assertTrue(review_retail_need_scope(frame).route_eligible.all())

    def test_own_anchored_description_can_identify_a_nonfood_role(self):
        frame=self.frame(['Ромашка'], tags_json=['{"description":"Магазин строительных материалов"}'])
        self.assertFalse(review_retail_need_scope(frame).route_eligible.iloc[0])

    def test_generic_brand_and_bread_name_do_not_prove_specialist_only_assortment(self):
        names=['Электроника', 'Мастерстрой', 'Хлеб и соль', 'Свежий хлеб', 'Двина']
        self.assertTrue(review_retail_need_scope(self.frame(names)).route_eligible.all())

    def test_other_service_family_and_prior_access_hold_are_preserved(self):
        frame=self.frame(['Магнит косметик','Продукты'],
                         service_code=['comparison_retail','daily_grocery'],route_eligible=[True,False])
        self.assertEqual(review_retail_need_scope(frame).route_eligible.tolist(), [True,False])

    def test_raw_source_claims_coordinates_and_ownership_are_immutable(self):
        frame=self.frame(['Стройматериалы'],source_record_id=['np'],site_lat=[50.],site_lon=[40.],
                         tags_json=['{"shop":"supermarket"}'])
        result=review_retail_need_scope(frame)
        pd.testing.assert_frame_equal(frame.drop(columns='route_eligible'),
                                      result[frame.columns].drop(columns='route_eligible'))

    def test_duplicate_dataframe_labels_do_not_spread_one_sites_conflict_to_another(self):
        frame=self.frame(['Продукты','Стройматериалы'])
        frame.index=[0,0]
        self.assertEqual(review_retail_need_scope(frame).route_eligible.tolist(),[True,False])


if __name__=='__main__':
    unittest.main()
