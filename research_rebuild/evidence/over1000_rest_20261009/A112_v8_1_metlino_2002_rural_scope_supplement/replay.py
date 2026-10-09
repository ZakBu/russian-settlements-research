import xlrd,sys
p=sys.argv[1]
w=xlrd.open_workbook(p,on_demand=True)
for s in w.sheets():
 for i in range(s.nrows):
  if any("метлино" in str(s.cell_value(i,j)).casefold() for j in range(s.ncols)):
   print(s.name,i+1,[s.cell_value(i,j) for j in range(min(10,s.ncols))])
