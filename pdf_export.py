"""
Модуль генерации PDF отчётов для врача
"""

import os
from datetime import datetime
from typing import List, Dict
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.lib.colors import HexColor
from reportlab.platypus import (
    SimpleDocTemplate, 
    Paragraph, 
    Spacer, 
    Table, 
    TableStyle,
    PageBreak
)
from reportlab.lib import colors
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

# Пытаемся зарегистрировать кириллический шрифт
try:
    # DejaVu Sans поддерживает кириллицу и обычно есть в Linux
    pdfmetrics.registerFont(TTFont('DejaVuSans', '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'))
    pdfmetrics.registerFont(TTFont('DejaVuSans-Bold', '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'))
    FONT_NAME = 'DejaVuSans'
    FONT_BOLD = 'DejaVuSans-Bold'
except:
    FONT_NAME = 'Helvetica'
    FONT_BOLD = 'Helvetica-Bold'


def generate_pdf_report(pet: Dict, records: List[Dict], reminders: List[Dict]) -> str:
    """
    Генерация PDF отчёта для врача
    
    Args:
        pet: данные питомца
        records: список записей
        reminders: список напоминаний
    
    Returns:
        путь к созданному PDF файлу
    """
    
    # Создаём временный файл
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"/tmp/pet_report_{pet['id']}_{timestamp}.pdf"
    
    # Настраиваем документ
    doc = SimpleDocTemplate(
        filename,
        pagesize=A4,
        rightMargin=20*mm,
        leftMargin=20*mm,
        topMargin=20*mm,
        bottomMargin=20*mm
    )
    
    # Создаём стили
    styles = getSampleStyleSheet()
    
    # Кастомные стили
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Title'],
        fontName=FONT_BOLD,
        fontSize=18,
        spaceAfter=10*mm,
        textColor=HexColor('#2C3E50')
    )
    
    heading_style = ParagraphStyle(
        'CustomHeading',
        parent=styles['Heading2'],
        fontName=FONT_BOLD,
        fontSize=14,
        spaceBefore=8*mm,
        spaceAfter=4*mm,
        textColor=HexColor('#34495E')
    )
    
    normal_style = ParagraphStyle(
        'CustomNormal',
        parent=styles['Normal'],
        fontName=FONT_NAME,
        fontSize=10,
        leading=14
    )
    
    small_style = ParagraphStyle(
        'CustomSmall',
        parent=styles['Normal'],
        fontName=FONT_NAME,
        fontSize=9,
        textColor=HexColor('#7F8C8D')
    )
    
    # Собираем контент
    story = []
    
    # === Заголовок ===
    story.append(Paragraph(
        f"История здоровья: {pet['name']}", 
        title_style
    ))
    
    # Информация о питомце
    story.append(Paragraph(
        f"Тип: {pet['type']}",
        normal_style
    ))
    
    report_date = datetime.now().strftime("%d.%m.%Y")
    story.append(Paragraph(
        f"Дата отчёта: {report_date}",
        small_style
    ))
    
    story.append(Spacer(1, 10*mm))
    
    # === Визиты к врачу ===
    visits = [r for r in records if r.get('is_visit')]
    if visits:
        story.append(Paragraph("Визиты к врачу", heading_style))
        
        visit_data = [["Дата", "Описание", "Тег"]]
        for visit in visits[:20]:
            date = format_date(visit['created_at'])
            text = truncate_text(visit.get('text') or visit.get('description') or '-', 50)
            tag = visit.get('tag') or '-'
            visit_data.append([date, text, tag])
        
        visit_table = create_table(visit_data)
        story.append(visit_table)
        story.append(Spacer(1, 5*mm))
    
    # === Записи (по категориям) ===
    story.append(Paragraph("Записи", heading_style))
    
    # Группируем по тегам
    tagged_records = {}
    untagged_records = []
    
    for record in records:
        if record.get('tag'):
            tag = record['tag']
            if tag not in tagged_records:
                tagged_records[tag] = []
            tagged_records[tag].append(record)
        else:
            untagged_records.append(record)
    
    # Выводим по категориям
    for tag, tag_records in sorted(tagged_records.items()):
        story.append(Paragraph(f"<b>{tag.capitalize()}</b>", normal_style))
        
        record_data = [["Дата", "Запись"]]
        for record in tag_records[:15]:
            date = format_date(record['created_at'])
            text = truncate_text(record.get('text') or '-', 60)
            record_data.append([date, text])
        
        record_table = create_table(record_data, col_widths=[35*mm, 120*mm])
        story.append(record_table)
        story.append(Spacer(1, 3*mm))
    
    # Остальные записи
    if untagged_records:
        story.append(Paragraph("<b>Прочие записи</b>", normal_style))
        
        record_data = [["Дата", "Запись"]]
        for record in untagged_records[:20]:
            date = format_date(record['created_at'])
            text = truncate_text(record.get('text') or '-', 60)
            record_data.append([date, text])
        
        record_table = create_table(record_data, col_widths=[35*mm, 120*mm])
        story.append(record_table)
    
    story.append(Spacer(1, 8*mm))
    
    # === Напоминания и лекарства ===
    if reminders:
        story.append(Paragraph("История напоминаний", heading_style))
        
        reminder_data = [["Дата", "Напоминание", "Статус"]]
        for reminder in reminders[:20]:
            date = format_date(reminder['created_at'])
            text = truncate_text(reminder['text'], 45)
            status = reminder['status']
            reminder_data.append([date, text, status])
        
        reminder_table = create_table(reminder_data, col_widths=[30*mm, 95*mm, 30*mm])
        story.append(reminder_table)
    
    # === Подвал ===
    story.append(Spacer(1, 15*mm))
    story.append(Paragraph(
        "Отчёт сгенерирован автоматически",
        small_style
    ))
    
    # Собираем документ
    doc.build(story)
    
    return filename


def format_date(date_str: str) -> str:
    """Форматирование даты"""
    try:
        dt = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
        return dt.strftime("%d.%m.%Y")
    except:
        return date_str[:10] if len(date_str) >= 10 else date_str


def truncate_text(text: str, max_length: int) -> str:
    """Обрезка текста с многоточием"""
    if len(text) <= max_length:
        return text
    return text[:max_length-3] + "..."


def create_table(data: List[List[str]], col_widths: List = None) -> Table:
    """Создание стилизованной таблицы"""
    
    if col_widths is None:
        col_widths = [35*mm, 85*mm, 35*mm]
    
    table = Table(data, colWidths=col_widths)
    
    style = TableStyle([
        # Заголовок
        ('BACKGROUND', (0, 0), (-1, 0), HexColor('#3498DB')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), FONT_BOLD),
        ('FONTSIZE', (0, 0), (-1, 0), 10),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
        ('TOPPADDING', (0, 0), (-1, 0), 8),
        
        # Тело таблицы
        ('FONTNAME', (0, 1), (-1, -1), FONT_NAME),
        ('FONTSIZE', (0, 1), (-1, -1), 9),
        ('BOTTOMPADDING', (0, 1), (-1, -1), 6),
        ('TOPPADDING', (0, 1), (-1, -1), 6),
        
        # Чередующиеся строки
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, HexColor('#ECF0F1')]),
        
        # Границы
        ('GRID', (0, 0), (-1, -1), 0.5, HexColor('#BDC3C7')),
        
        # Выравнивание
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ])
    
    table.setStyle(style)
    return table
