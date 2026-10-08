exec(open('/workspace/settlements-work/large_absorbed_city_closed_scope_mass_20261008/scan.py').read().split('configs=')[0])
O=E/'city_territory_mass_followup_20261008'
names={'Екатеринбург':'свердловская','Барнаул':'алтайский','Якутск':'саха якутия','Владимир':'владимирская','Киров':'кировская'}
for name,region in names.items():
 print('\nCITY',name)
 city=o[o.name_norm.eq(name.lower())&o.region_norm.eq(region)&o.type_norm.eq('город')]
 print(city[['census_year','source_file','source_sheet','source_row','population']].to_string(index=False))
 regionrows=o[o.region_norm.eq(region)&o.census_year.isin([2002,2010])]; print('files',regionrows[['census_year','source_file','source_sheet']].drop_duplicates().to_dict('records'))
 c=city[city.census_year.eq(2021)].iloc[0];rs=raw.iloc[int(c.source_row)-1];scope=raw[raw.region.eq(rs.region)&raw.mun_upper.eq(rs.mun_upper)];print(scope[['object_level','object_name','population']].to_string())
 for year in [2002,2010]:
  for file in regionrows[regionrows.census_year.eq(year)].source_file.unique():
   if not file.endswith('.xls'):continue
   book=xlrd.open_workbook(str(Path('/workspace/settlements-raw')/file))
   for sheet in book.sheets():
    hits=[n for n in range(sheet.nrows) if any(isinstance(v,str) and name.lower() in v.lower() for v in sheet.row_values(n))]
    if hits:
     print('RAW',year,file,sheet.name,'hits',hits[:12])
     for hit in hits[:1]:
      for n in range(max(0,hit-1),min(sheet.nrows,hit+40)):print(n+1,sheet.row_values(n)[:10])
