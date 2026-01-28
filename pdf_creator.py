"""
Создание PDF из изображений
"""

import os
from pathlib import Path
from datetime import datetime
from typing import List

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from PIL import Image


def create_pdf_from_images(image_paths: List[str], user_id: int) -> str:
    """
    Создаёт PDF из списка изображений
    
    Args:
        image_paths: список путей к изображениям
        user_id: ID пользователя (для имени файла)
    
    Returns:
        путь к созданному PDF
    """
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    pdf_path = f"/tmp/photos_{user_id}_{timestamp}.pdf"
    
    # Размер страницы A4
    page_width, page_height = A4
    
    c = canvas.Canvas(pdf_path, pagesize=A4)
    
    for i, img_path in enumerate(image_paths):
        if not os.path.exists(img_path):
            continue
        
        try:
            # Открываем изображение для получения размеров
            with Image.open(img_path) as img:
                img_width, img_height = img.size
                
                # Конвертируем RGBA в RGB если нужно
                if img.mode == 'RGBA':
                    rgb_img = Image.new('RGB', img.size, (255, 255, 255))
                    rgb_img.paste(img, mask=img.split()[3])
                    temp_path = img_path + "_temp.jpg"
                    rgb_img.save(temp_path, "JPEG")
                    img_path = temp_path
            
            # Вычисляем масштаб, чтобы изображение поместилось на страницу
            # Оставляем отступы 20 точек с каждой стороны
            margin = 20
            available_width = page_width - 2 * margin
            available_height = page_height - 2 * margin
            
            # Масштабируем пропорционально
            scale_w = available_width / img_width
            scale_h = available_height / img_height
            scale = min(scale_w, scale_h)
            
            new_width = img_width * scale
            new_height = img_height * scale
            
            # Центрируем на странице
            x = (page_width - new_width) / 2
            y = (page_height - new_height) / 2
            
            # Добавляем изображение
            c.drawImage(img_path, x, y, width=new_width, height=new_height)
            
            # Удаляем временный файл если создавали
            if img_path.endswith("_temp.jpg"):
                os.remove(img_path)
            
            # Новая страница для следующего изображения
            if i < len(image_paths) - 1:
                c.showPage()
                
        except Exception as e:
            print(f"Ошибка обработки {img_path}: {e}")
            continue
    
    c.save()
    return pdf_path
