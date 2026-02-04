"""
Модуль генерации PDF отчётов для врача
"""

import os
from datetime import datetime
from typing import List, Dict, Optional
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
    PageBreak,
    Image,
)
from reportlab.lib import colors
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

# Пытаемся зарегистрировать кириллический шрифт
FONT_NAME = "Helvetica"
FONT_BOLD = "Helvetica-Bold"

def _init_cyrillic_font():
    """Инициализация шрифта с поддержкой кириллицы.

    Приоритет:
    1. Путь из переменной окружения PDF_FONT_PATH
    2. Распространённые пути DejaVu / Arial в Linux/macOS
    3. Фоллбек на стандартный Helvetica (может не поддерживать кириллицу)
    """
    global FONT_NAME, FONT_BOLD

    candidates = []

    env_font = os.environ.get("PDF_FONT_PATH")
    if env_font:
        candidates.append((env_font, None))

    # Linux (наш Docker)
    candidates.append(
        (
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        )
    )

    # Возможные пути на macOS
    candidates.append(
        (
            "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
            None,
        )
    )
    candidates.append(
        (
            "/System/Library/Fonts/Supplemental/Arial.ttf",
            "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
        )
    )

    for regular_path, bold_path in candidates:
        try:
            if not os.path.exists(regular_path):
                continue

            pdfmetrics.registerFont(TTFont("CustomCyrillic", regular_path))
            FONT_NAME = "CustomCyrillic"

            if bold_path and os.path.exists(bold_path):
                pdfmetrics.registerFont(TTFont("CustomCyrillic-Bold", bold_path))
                FONT_BOLD = "CustomCyrillic-Bold"
            else:
                FONT_BOLD = FONT_NAME

            return
        except Exception:
            continue


_init_cyrillic_font()


def generate_pdf_report(
    pet: Dict,
    records: List[Dict],
    reminders: List[Dict],
    pet_photo_path: Optional[str] = None,
) -> str:
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

    # Фото питомца (если есть)
    if pet_photo_path and os.path.exists(pet_photo_path):
        try:
            img = Image(pet_photo_path, width=40 * mm, height=40 * mm)
            img.hAlign = "RIGHT"
            story.append(img)
            story.append(Spacer(1, 5 * mm))
        except Exception:
            # Если по какой-то причине изображение не вставилось — просто пропускаем
            pass
    
    # Информация о питомце
    pet_type = pet.get("type", "")
    story.append(Paragraph(
        f"Тип: {pet_type}",
        normal_style
    ))

    # Дополнительные данные из анкеты
    details_lines = []

    gender_map = {"м": "мальчик", "ж": "девочка"}
    gender_raw = pet.get("gender")
    if gender_raw:
        details_lines.append(f"Пол: {gender_map.get(gender_raw, gender_raw)}")

    if pet.get("breed"):
        details_lines.append(f"Порода: {pet['breed']}")

    if pet.get("birth_date"):
        details_lines.append(f"Дата рождения: {pet['birth_date']}")

    if pet.get("weight") is not None:
        details_lines.append(f"Вес: {pet['weight']} кг")

    if pet.get("vaccinations"):
        details_lines.append(f"Вакцинация: {pet['vaccinations']}")

    if pet.get("owner_name"):
        details_lines.append(f"Владелец: {pet['owner_name']}")

    if details_lines:
        story.append(Paragraph(
            "<br/>".join(details_lines),
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
