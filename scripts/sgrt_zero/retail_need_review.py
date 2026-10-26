"""Hold explicit nonfood-assortment contradictions without claiming closure.

An OSM general-food tag is a positive source claim, not proof that an own-name
hardware or furniture shop supplies a general grocery need. Mixed food/nonfood
shops remain eligible. Operator/brand labels inherited from another entity are
never read as this site's own assortment.
"""
from __future__ import annotations

import json
import re
import pandas as pd

GROCERY_SERVICES = {'daily_grocery', 'daily_grocery_current_retail_host'}
FOOD = re.compile(
    r'\b(?:еда|продукт[а-я]*|продовольств[а-я]*|бакале[а-я]*)\b'
    r'|\bпрод(?:маг|промтовар|[/.\s-]+хоз|\s*товар)|хоз[- /]*прод', re.I)
NONHUMAN_FOOD = re.compile(r'(?:продукт[а-я]*|питани[а-я]*|еда)\s+для\s+'
    r'(?:домашн[а-я]*\s+)?(?:животн[а-я]*|питомц[а-я]*|кошек|собак|птиц)', re.I)
NONFOOD = re.compile(
    r'стройматериал|строительн[а-я]*\s+(?:и\s+отделочн[а-я]*\s+)?материал'
    r'|\bстрой(?:база|депо|маркет|оптторг)\b'
    r'|\bсантехник[а-я]*\b|\bсантех\s+маг\b'
    r'|\b(?:авто|автотракторо|мото|тракторо)запчаст[а-я]*\b'
    r'|\bмебельн[а-я]*\s+(?:салон|магазин|универсам|супермаркет|компани[а-я]*|баз[а-я]*)\b'
    r'|\b(?:интер[- ]?)?мебел[ьи]\b|^\s*мебельный\s*$'
    r'|\b(?:канцелярск[а-я]*\s+товар[а-я]*|канцтовар[а-я]*|зоотовар[а-я]*)\b'
    r'|\bбытов[а-я]*\s+хими[а-я]*\b|\bхозтовар[а-я]*\b'
    r'|\b(?:промтовар[а-я]*|электротовар[а-я]*|автомагазин|аптек[а-я]*)\b'
    r'|\b(?:табак|табачн[а-я]*\s+магазин|сигарет[а-я]*|спецодежд[а-я]*)\b'
    r'|\bодежда\s+и\s+обувь\b|^\s*(?:одежда|обувь)\s*$'
    r'|\bмагазин\s+(?:(?:женск[а-я]*|мужск[а-я]*|детск[а-я]*)\s+)?'
    r'(?:одежды|обуви|мебели|автозапчастей|электроники|косметик[а-я]*)\b'
    r'|\bцветочн[а-я]*\s+магазин\b|\bмагазин\s+цветов\b'
    r'|\bсалон\s+красоты\b|\bпарикмахерская\b', re.I)
COSMETIC_FORMAT = re.compile(r'\bмагнит\s*[-–—"«»]?\s*косметик[са]?\b|\b[мm]\s*[.]\s*косметик\b'
                             r'|\bmagnit\s*[-–—]?\s*cosmeti[ck]\b', re.I)
MAGNIT_WORD = re.compile(r'\bмагнит\b|\bmagnit\b', re.I)


def _text(value):
    return value.strip().casefold().replace('ё', 'е') if isinstance(value, str) else ''


def _tags(value):
    if isinstance(value, dict):
        return value
    try:
        parsed=json.loads(value) if isinstance(value,str) else {}
        return parsed if isinstance(parsed,dict) else {}
    except (TypeError, ValueError):
        return {}


def retail_need_scope_reason(row):
    """Return a bounded own-assortment conflict; generic names are not errors."""
    if row.get('service_code') not in GROCERY_SERVICES:
        return ''
    tags = _tags(row.get('tags_json', row.get('source_tags_json')))
    names = [_text(row.get(key)) for key in ['source_name', 'name', 'site_name']]
    names += [_text(tags.get(key)) for key in ['name', 'official_name', 'name:ru', 'name:en']]
    # A description of this shop can corroborate an explicit category. An
    # unanchored direction such as "opposite the furniture shop" cannot.
    description = _text(tags.get('description'))
    if re.match(r'^(?:магазин|салон|торговый\s+салон|продажа)\s+'
                r'(?:стройматериал|строительн|сантех|мебел|одежд|обув|авто|мото|хозтов|бытов|канцеляр|зоотов|красот)',
                description):
        names.append(description)
    names = list(dict.fromkeys(value for value in names if value))
    if not names or any(FOOD.search(NONHUMAN_FOOD.sub('',value)) for value in names):
        return ''
    mixed_magnit=any(COSMETIC_FORMAT.search(value) and len(MAGNIT_WORD.findall(value))>1
                     for value in names)
    for value in names:
        if COSMETIC_FORMAT.search(value) and not mixed_magnit:
            # One mapped feature may explicitly describe both a food Magnit
            # and a Magnit Cosmetic. Do not turn that mixed site into absence.
            if len(MAGNIT_WORD.findall(value)) <= 1:
                return 'explicit_cosmetics_household_format_general_grocery_not_established'
        if NONFOOD.search(value):
            return 'explicit_own_nonfood_assortment_conflicts_with_general_grocery_tag'
    return ''


def review_retail_need_scope(frame):
    """Preserve raw claims; hold ambiguous general-grocery use only."""
    result = frame.copy()
    result['route_eligible'] = result.get('route_eligible', pd.Series(True, index=result.index)).map(
        lambda value: False if pd.isna(value) else value is True or value == 1
        or str(value).casefold() in {'true', '1', '1.0', 'yes'})
    result['retail_need_scope_review_reason'] = ''
    mask=result.service_code.isin(GROCERY_SERVICES)
    fields=[c for c in ['service_code','source_name','name','site_name','tags_json','source_tags_json']
            if c in result]
    # Do not materialize the whole national source as half a million wide dicts.
    reasons=[retail_need_scope_reason(dict(zip(fields,values)))
             for values in result.loc[mask,fields].itertuples(index=False,name=None)]
    result.loc[mask,'retail_need_scope_review_reason']=reasons
    result.loc[result.retail_need_scope_review_reason.ne(''), 'route_eligible'] = False
    result['retail_scope_review_does_not_establish_closure_or_no_food_sales'] = True
    return result
