# Generate PWA icons using PIL
from PIL import Image, ImageDraw, ImageFont
import os

sizes = [72, 96, 128, 144, 152, 192, 384, 512]

for size in sizes:
    img = Image.new('RGB', (size, size), '#1F4E79')
    draw = ImageDraw.Draw(img)
    
    # White rounded rectangle background
    margin = size // 8
    draw.rounded_rectangle([margin, margin, size-margin, size-margin], 
                          radius=size//6, fill='#2E75B6')
    
    # Text "U" for UCSRS
    font_size = size // 2
    try:
        font = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf', font_size)
    except:
        font = ImageFont.load_default()
    
    text = 'U'
    bbox = draw.textbbox((0, 0), text, font=font)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    x = (size - tw) // 2
    y = (size - th) // 2 - size//12
    draw.text((x, y), text, fill='white', font=font)
    
    # Small text "UCSRS"
    try:
        small_font = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf', size//8)
    except:
        small_font = ImageFont.load_default()
    
    sub = 'UCSRS'
    sbbox = draw.textbbox((0, 0), sub, font=small_font)
    sw = sbbox[2] - sbbox[0]
    draw.text(((size-sw)//2, size*3//4 - size//14), sub, fill='white', font=small_font)
    
    img.save(f'/home/claude/ucsrs_pwa/icon-{size}x{size}.png')
    print(f'Generated icon-{size}x{size}.png')

print('All icons generated')
