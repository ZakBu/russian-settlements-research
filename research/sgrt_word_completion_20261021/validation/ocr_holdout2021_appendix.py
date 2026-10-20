from pathlib import Path
import fitz,subprocess,concurrent.futures,os,time
R=Path('/workspace/scratch/sgrt_holdout2021');D=R/'ocr';D.mkdir(exist_ok=True)
# Requires rus.traineddata (SHA e16e5e036cce1d9ec2b00063cf8b54472625b9e14d893a169e2b0dedeb4df225) in R; tesseract-ocr/tessdata_fast GitHub.
def run(page):
 out=D/f'page_{page:03d}';txt=out.with_suffix('.txt')
 if txt.exists():return page
 d=fitz.open(R/'kaluga2021_official_http_pdf.pdf');pg=d[page-1];pg.get_pixmap(matrix=fitz.Matrix(2,2),clip=fitz.Rect(0,0,420,595)).save(out.with_suffix('.png'));d.close()
 env=dict(os.environ,OMP_THREAD_LIMIT='1');subprocess.run(['tesseract',str(out.with_suffix('.png')),str(out),'--tessdata-dir',str(R),'-l','rus','--psm','6'],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,env=env);return page
with concurrent.futures.ThreadPoolExecutor(2) as ex:
 for n,p in enumerate(ex.map(run,range(29,95)),1):
  if n%10==0:print(n,'/66',flush=True)
