from pathlib import Path
from PIL import Image,ImageDraw
root=Path(__file__).resolve().parents[1]/'screenshots'
names=['visual-desktop-ubs-viewport','visual-desktop-ubs-repo-ubs-engine-viewport','visual-desktop-ubs-repo-ubs-engine-quality-viewport','visual-desktop-method-viewport','visual-desktop-triton-viewport','visual-tablet-triton-viewport','ubs-ham-viewport','ubs-ubs-comm-viewport','ubs-OmniStateStore-quality-viewport']
canvas=Image.new('RGB',(1800,1350),'#e5e7eb');draw=ImageDraw.Draw(canvas)
for i,n in enumerate(names):
 im=Image.open(root/(n+'.png')).convert('RGB');im.thumbnail((592,410));x=(i%3)*600;y=(i//3)*450;canvas.paste(im,(x,y+28));draw.text((x+8,y+8),n,fill='black')
canvas.save(root/'contact-sheet.png')
im=Image.open(root/'visual-mobile-triton.png');im.crop((0,1000,390,2500)).save(root/'mobile-triton-charts-crop.png')
im=Image.open(root/'ubs-detail.png');im.crop((0,0,1440,min(1600,im.height))).save(root/'ubs-detail-crop.png')
