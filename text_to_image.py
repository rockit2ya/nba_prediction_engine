#!/usr/bin/env python3
"""Render a text file as a single PNG image (full-length, no scrolling needed)."""
import sys
from PIL import Image, ImageDraw, ImageFont

def text_to_image(input_path, output_path=None):
    if output_path is None:
        output_path = input_path.rsplit('.', 1)[0] + '.png'

    with open(input_path, 'r') as f:
        lines = f.readlines()

    # Use a monospace font
    try:
        font = ImageFont.truetype("/System/Library/Fonts/Menlo.ttc", 14)
    except Exception:
        font = ImageFont.load_default()

    # Measure dimensions
    line_height = 18
    padding = 30
    max_width = max(font.getlength(line.rstrip('\n')) for line in lines) if lines else 400
    img_width = int(max_width + padding * 2)
    img_height = int(len(lines) * line_height + padding * 2)

    # Dark terminal-style background
    img = Image.new('RGB', (img_width, img_height), color=(30, 30, 30))
    draw = ImageDraw.Draw(img)

    y = padding
    for line in lines:
        text = line.rstrip('\n')
        # Color coding for visual appeal
        if any(k in text for k in ['✅', 'WIN', 'SUCCESS', '🏆', '🔥']):
            color = (80, 220, 100)
        elif any(k in text for k in ['❌', 'LOSS', 'ERROR', '🔴']):
            color = (255, 90, 90)
        elif any(k in text for k in ['⚠️', 'VERDICT', '📈', '🚨']):
            color = (255, 200, 60)
        elif any(k in text for k in ['═', '─', '•']):
            color = (120, 120, 140)
        elif any(k in text for k in ['📊', '💰', '🏀', '📅', '🏁']):
            color = (100, 180, 255)
        else:
            color = (210, 210, 210)
        draw.text((padding, y), text, font=font, fill=color)
        y += line_height

    img.save(output_path)
    print(f"✅ Saved: {output_path} ({img_width}x{img_height}px)")

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python text_to_image.py <input.txt> [output.png]")
        sys.exit(1)
    out = sys.argv[2] if len(sys.argv) > 2 else None
    text_to_image(sys.argv[1], out)
