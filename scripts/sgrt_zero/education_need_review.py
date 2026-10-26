"""Hold explicitly unsuitable school roles without rewriting their raw claims.

The source ``amenity=school`` is a broad proxy. Named nurseries, workplaces,
supplementary courses and universities do not establish ordinary child general
school provision. Generic names, an IT focus and parent operators do not prove
the contrary either. This review invents no programme, location or closure.
"""
from __future__ import annotations

import re
from urllib.parse import urlsplit
import pandas as pd

from scripts.sgrt_zero.education import (
    semantic_education_text, semantic_programme_tags,
)


def _text(value):
    return re.sub(r'\s+', ' ', semantic_education_text(value).replace('\u200b', '').lower().replace('ё', 'е')).strip()


def _truth(value, default=False):
    if value is None or pd.isna(value):
        return default
    return value is True or value == 1 or str(value).lower() in {'true', '1', '1.0', 'yes'}


def _own_names(row, tags):
    # Parent operators, websites, founders and brands in description are not
    # physical-site names. They cannot by themselves exclude a real school.
    values = [row.get('name'), row.get('provider_name'), row.get('source_name')]
    values += [tags.get(k) for k in ['name', 'official_name', 'alt_name', 'name:ru', 'name:en']]
    return ' '.join(dict.fromkeys(v for v in map(_text, values) if v))


def _general_signal(names, tags, row):
    verified = any(_truth(row.get(k)) for k in ['general_school_programme_verified',
                  'general_education_programme_verified', 'function_assignment_verified_by_licence'])
    # In Russian statutory terminology supplementary courses can be called
    # "дополнительные общеобразовательные программы". That phrase does not
    # establish a basic general-school curriculum at a named extra centre.
    programme_names=re.sub(r'дополнительн\w*\s+(?:общеразвивающ\w*\s+)?'
        r'общеобразовательн\w*\s+программ\w*',' ',names)
    named = bool(re.search(r'общеобразовательн|общего\s+образован|гимназ|'
                          r'\b(?:сош|оош|нош)\b|(?:начальн|основн|средн)\w*\s+'
                          r'(?:общеобразовательн\w*\s+)?школ|школ\w*\s+с\s+углубленн', programme_names))
    named |= bool(re.search(r'\bлицей\b',programme_names)) and not bool(re.search(
        r'профессиональн\w*\s+лицей|\bпроф\.?\s*лицей',programme_names))
    # ISCED3 includes vocational education. Numeric stages/grades describe a
    # level, not the programme kind; they cannot turn a ПТУ or nursery into a
    # general school. A literal general profile is still only a source proxy.
    typed = str(tags.get('education_profile:general', '')).lower() == 'yes'
    typed |= any(str(tags.get(k, '')).lower() == 'yes' for k in
                 ['education_level:primary', 'education_level:secondary'])
    return verified or named or typed


def school_role_review_reason(row):
    """Return (reason, positive-signal-conflict) for an individual raw card.

    Explicit positive general-school evidence prevents an inference from a
    supplementary brand, technical focus or religious/vocational name. Clear
    physical-site roles such as a nursery-only building or an induction room
    remain different services; a combined primary-school/nursery is protected.
    """
    tags = semantic_programme_tags(row.get('tags_json', row.get('source_tags_json')))
    names = _own_names(row, tags)
    general = _general_signal(names, tags, row)
    verified = any(_truth(row.get(k)) for k in ['general_school_programme_verified',
                   'general_education_programme_verified', 'function_assignment_verified_by_licence'])
    primary_name = _text(row.get('name', row.get('provider_name', row.get('source_name'))))
    # Mixed school/nursery campuses (including abbreviated НОШ-ДС) do exist.
    # A nursery word in an alias must not erase a named general school.
    combined = bool(re.search(r'\bшкол\w*|\bн[о]?ш(?:дс)?\b|гимназ|\bлицей\b', primary_name))
    preschool_department = bool(re.search(r'\(\s*(?:детск\w*\s+сад|дошкольн\w*\s+отделени)|'
        r'\bдошкольн\w*\s+отделени', primary_name))
    if preschool_department:
        combined = False
    nursery = bool(re.search(r'детск\w*\s+сад|\bясли(?:[- ]сад)?\b|\bсадик\b|\bд\s*/\s*с\b|'
                             r'\b(?:мбдоу|мдоу|мдобу|мдадоу|мдодоу)\b|\bмк\s+доу\b', names))
    if nursery and not combined and not verified:
        if general and not preschool_department:
            # A short name or even an acronym may be incomplete/incorrect.
            # Preserve explicit full school/combined-school evidence from the
            # own official name instead of deleting an actual primary school.
            return '', True
        return 'named_preschool_only_site_not_general_school_programme', general
    if re.search(r'кабинет\w*\s+(?:вводн\w*\s+)?инструктаж', names):
        return 'named_workplace_induction_room_not_general_school', general
    if re.search(r'\bмфц\b|социальн\w*\s+участков|объект\w*\s+здравоохранени|'
                 r'бывш\w*\s+сестринск\w*\s+корпус|лыжн\w*\s+стадион|конн\w*\s+дворик', names):
        if not general:
            return 'named_civic_health_social_or_sport_site_not_general_school', False

    reason = ''
    own_site = str(tags.get('website',tags.get('contact:website','')) or '').strip()
    try:
        own_host = urlsplit(own_site if '://' in own_site else 'https://'+own_site).hostname or ''
    except ValueError:
        own_host = ''
    reviewed_language_centre = (own_host.lower().removeprefix('www.') == 'rub-lingvo.ru'
        and bool(re.search(r'\bлингва\b',names)))
    if re.search(r'\bkiber\s*[- ]?\s*one\b|\bкибер\s*[- ]?\s*(?:one|ван|уан)\b', names):
        # The reviewed own KIBERone programme is supplementary child IT
        # training; neither an operator field nor website alone triggers this.
        reason = 'named_supplementary_child_IT_brand_general_programme_not_established'
    elif reviewed_language_centre:
        # The own linked centre's reviewed programme offers language courses.
        # Neither the generic name Lingva nor a website field alone is enough.
        reason = 'own_reviewed_language_centre_programme_not_general_school'
    elif re.search(r'центр\w*\s+развити\w*\s+(?:и\s+)?творчест|'
                   r'дом\w*\s+пионер|'
                   r'\b(?:цдтт|цртдию|црдию|цвр)\b|\bм[бк]у\s+до\b', names):
        reason = 'named_supplementary_creativity_or_extracurricular_centre'
    elif re.search(r'центр\w*\s+раннего\s+развития|школ\w*\s+раннего\s+развития|'
                   r'школ\w*\s+развития\s+малыша|(?:центр|академи)\w*\s+ментальн\w*\s+арифметик', names):
        reason = 'named_early_childhood_or_mental_arithmetic_training_not_general_school'
    elif re.search(r'english\s+club|social\s+english\s+club|\blanguage\s+club\b|'
                   r'языков\w*\s+клуб|(?:курс|клуб)\w*\s+(?:английск|иностранн)\w*\s+язык|'
                   r'ал[ья]ян[сc]ь?\s+франсез', names):
        reason = 'named_language_club_or_language_courses_not_general_school'
    elif re.search(r'\bвпо\b|\b(?:спту|пту)(?=\b|\d)|\bпу\s*№?\s*\d|сельскохозяйственн\w*\s+академи|'
                   r'высш\w*\s+коммерческ\w*\s+школ|профессиональн\w*\s+(?:лицей|училище)|\bпроф\.?\s*лицей|'
                   r'\bколедж\b|филиал\s+дгту|\bртжт\b', names):
        reason = 'named_vocational_or_higher_institution_general_school_programme_unestablished'
    elif re.search(r'медресе|духовн\w*\s+семинари', names):
        reason = 'named_religious_training_general_school_programme_unestablished'
    else:
        description = _text(tags.get('description'))
        explicit_technical_type = bool(re.match(r'^(?:школ\w*|курс\w*|учебн\w*\s+центр)\s+'
            r'(?:по\s+)?(?:программирован|робототех)', description))
        technical_name = bool(re.search(r'robo\s*code|робо\s*код|школ\w*\s+программирован|'
            r'(?:школ|центр|академи)\w*\s+робототех', names))
        if explicit_technical_type or technical_name:
            reason = 'own_site_explicit_coding_or_robotics_training_not_general_programme'
    if reason and general:
        return '', True
    return reason, False


def review_education_need_scope(frame):
    """Add reversible routing holds; preserve raw functions and source claims."""
    result = frame.copy()
    result['route_eligible'] = result.get('route_eligible', pd.Series(True, index=result.index)).map(_truth)
    result['source_education_need_review_reason'] = ''
    result['source_education_need_review_status'] = 'not_general_school_channel'
    result['source_education_need_review_conflicting_general_signal'] = False
    result['source_education_need_review_is_operational_or_licence_verification'] = False
    result['source_education_need_review_stage_tags_are_not_programme_kind_proof'] = True
    claimed = result.service_code.eq('school_general')
    result.loc[claimed, 'source_education_need_review_status'] = 'no_explicit_contradiction_identified_not_verified_general_curriculum'
    admitted = claimed & result.supply_status.isin(['observed', 'proxy'])
    if 'eligible' in result:
        admitted &= result.eligible.map(_truth)
    for idx, row in result.loc[admitted].iterrows():
        reason, conflict = school_role_review_reason(row)
        result.at[idx, 'source_education_need_review_conflicting_general_signal'] = conflict
        if reason:
            result.at[idx, 'route_eligible'] = False
            result.at[idx, 'source_education_need_review_reason'] = reason
            result.at[idx, 'source_education_need_review_status'] = 'held_explicit_non_general_or_unsuitable_site_role'
        elif conflict:
            result.at[idx, 'source_education_need_review_status'] = 'retained_explicit_general_signal_with_conflicting_supplementary_description'
    return result
