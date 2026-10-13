from pathlib import Path
from PIL import Image
import subprocess,concurrent.futures,time,json
p=Path('/workspace/shared/extended-population-20261013');tasks=[]
def task(page):
 src=p/f'bulk-{page:03d}.png'
 for attempt in range(1800):
  if src.exists():
   try:
    im=Image.open(src);im.load();break
   except:pass
  time.sleep(1)
 else:raise RuntimeError(str(src))
 w,h=im.size
 for side,box in [('left',(0,0,w//2,h)),('right',(w//2,0,w,h))]:
  stem=p/f'ocr_{page:03d}_{side}';im.crop(box).save(stem.with_suffix('.png'))
  subprocess.run(['tesseract',str(stem.with_suffix('.png')),str(stem),'--tessdata-dir',str(p/'tessdata'),'-l','rus','--psm','6','tsv'],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,env={'OMP_THREAD_LIMIT':'1'})
 return page
with concurrent.futures.ThreadPoolExecutor(4) as pool:
 for page in pool.map(task,range(85,126)):print('OCR',page,flush=True)
