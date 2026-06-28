"""
Chart Generator for Agents
"""

import json
import math
from pathlib import Path
from typing import Dict, List, Tuple


class ChartGenerator:
    """
    کلاس تولید نمودارهای SVG برای نمایش پیشرفت
    """
    
    def __init__(self, base_path: str = "/workspace/unified_agent"):
        self.base_path = Path(base_path)
        
    def generate_doughnut_chart(self, app_name: str) -> str:
        """
        تولید نمودار دونات پیشرفت
        
        Args:
            app_name: نام اپلیکیشن
            
        Returns:
            محتوای فایل SVG
        """
        app_path = self.base_path / "apps" / app_name
        progress_file = app_path / "PROGRESS.json"
        
        # خواندن داده‌های پیشرفت
        if not progress_file.exists():
            return self._create_empty_chart()
        
        with open(progress_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        overall_progress = data.get('overall_progress', 0)
        tasks = data.get('tasks', [])
        
        # محاسبه آمار وضعیت‌ها
        status_counts = {
            'completed': 0,
            'in_progress': 0,
            'not_started': 0,
            'blocked': 0,
            'cancelled': 0
        }
        
        for task in tasks:
            status = task.get('status', 'not_started')
            if status in status_counts:
                status_counts[status] += 1
        
        # تولید SVG
        svg_content = self._create_doughnut_svg(
            overall_progress,
            status_counts,
            app_name
        )
        
        # ذخیره در فایل
        chart_path = app_path / "charts" / "progress_doughnut.svg"
        chart_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(chart_path, 'w', encoding='utf-8') as f:
            f.write(svg_content)
        
        return svg_content
    
    def _create_doughnut_svg(self, progress: int, status_counts: Dict[str, int],
                           app_name: str) -> str:
        """ایجاد SVG نمودار دونات"""
        
        # تنظیمات نمودار
        width = 400
        height = 400
        cx = width // 2
        cy = height // 2
        outer_radius = 120
        inner_radius = 60
        
        # رنگ‌ها
        colors = {
            'completed': '#27ae60',
            'in_progress': '#3498db',
            'not_started': '#95a5a6',
            'blocked': '#e74c3c',
            'cancelled': '#e67e22'
        }
        
        # محاسبه مجموع
        total = sum(status_counts.values())
        if total == 0:
            return self._create_empty_chart()
        
        svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">
  <style>
    .title {{ font-family: Arial, sans-serif; font-size: 20px; font-weight: bold; fill: #2c3e50; }}
    .subtitle {{ font-family: Arial, sans-serif; font-size: 14px; fill: #7f8c8d; }}
    .percentage {{ font-family: Arial, sans-serif; font-size: 36px; font-weight: bold; fill: #2c3e50; }}
    .label {{ font-family: Arial, sans-serif; font-size: 12px; fill: #34495e; }}
    .legend-text {{ font-family: Arial, sans-serif; font-size: 12px; fill: #2c3e50; }}
  </style>
  
  <!-- عنوان -->
  <text x="{cx}" y="30" class="title" text-anchor="middle">{app_name.replace('_', ' ').title()}</text>
  <text x="{cx}" y="50" class="subtitle" text-anchor="middle">وضعیت پیشرفت</text>
'''
        
        # رسم نمودار دونات
        start_angle = -90  # شروع از بالا
        
        for status, count in status_counts.items():
            if count == 0:
                continue
                
            # محاسبه زاویه
            angle = (count / total) * 360
            end_angle = start_angle + angle
            
            # رسم بخش
            path = self._create_arc_path(
                cx, cy, outer_radius, inner_radius,
                start_angle, end_angle
            )
            
            svg += f'  <path d="{path}" fill="{colors[status]}" stroke="white" stroke-width="2"/>\n'
            
            start_angle = end_angle
        
        # نمایش درصد کلی در وسط
        svg += f'''
  <!-- درصد کلی -->
  <text x="{cx}" y="{cy + 10}" class="percentage" text-anchor="middle">{progress}%</text>
  <text x="{cx}" y="{cy + 30}" class="label" text-anchor="middle">پیشرفت کلی</text>
'''
        
        # راهنما (Legend)
        legend_y = 280
        legend_x = 50
        
        svg += '\n  <!-- راهنما -->\n'
        
        status_labels = {
            'completed': 'تکمیل شده',
            'in_progress': 'در حال انجام',
            'not_started': 'شروع نشده',
            'blocked': 'مسدود',
            'cancelled': 'لغو شده'
        }
        
        for i, (status, count) in enumerate(status_counts.items()):
            if count == 0:
                continue
                
            y = legend_y + (i * 25)
            percentage = (count / total) * 100
            
            svg += f'''  <rect x="{legend_x}" y="{y}" width="15" height="15" fill="{colors[status]}" rx="2"/>
  <text x="{legend_x + 20}" y="{y + 12}" class="legend-text">{status_labels[status]}: {count} ({percentage:.1f}%)</text>
'''
        
        svg += '</svg>'
        return svg
    
    def _create_arc_path(self, cx: int, cy: int, outer_radius: int,
                        inner_radius: int, start_angle: float,
                        end_angle: float) -> str:
        """ایجاد مسیر SVG برای قوس"""
        
        # تبدیل زاویه به رادیان
        start_rad = math.radians(start_angle)
        end_rad = math.radians(end_angle)
        
        # محاسبه نقاط
        x1_outer = cx + outer_radius * math.cos(start_rad)
        y1_outer = cy + outer_radius * math.sin(start_rad)
        x2_outer = cx + outer_radius * math.cos(end_rad)
        y2_outer = cy + outer_radius * math.sin(end_rad)
        
        x1_inner = cx + inner_radius * math.cos(start_rad)
        y1_inner = cy + inner_radius * math.sin(start_rad)
        x2_inner = cx + inner_radius * math.cos(end_rad)
        y2_inner = cy + inner_radius * math.sin(end_rad)
        
        # تعیین large-arc-flag
        large_arc = 1 if (end_angle - start_angle) > 180 else 0
        
        # ساخت مسیر
        path = f"M {x1_outer:.2f},{y1_outer:.2f} "
        path += f"A {outer_radius},{outer_radius} 0 {large_arc},1 {x2_outer:.2f},{y2_outer:.2f} "
        path += f"L {x2_inner:.2f},{y2_inner:.2f} "
        path += f"A {inner_radius},{inner_radius} 0 {large_arc},0 {x1_inner:.2f},{y1_inner:.2f} "
        path += "Z"
        
        return path
    
    def _create_empty_chart(self) -> str:
        """ایجاد نمودار خالی"""
        return '''<svg xmlns="http://www.w3.org/2000/svg" width="400" height="400" viewBox="0 0 400 400">
  <style>
    .message { font-family: Arial, sans-serif; font-size: 16px; fill: #7f8c8d; }
  </style>
  <text x="200" y="200" class="message" text-anchor="middle">داده‌ای برای نمایش وجود ندارد</text>
</svg>'''
    
    def generate_gantt_chart(self, app_name: str) -> str:
        """
        تولید نمودار گانت برای تسک‌ها
        
        Args:
            app_name: نام اپلیکیشن
            
        Returns:
            محتوای فایل SVG
        """
        app_path = self.base_path / "apps" / app_name
        progress_file = app_path / "PROGRESS.json"
        
        if not progress_file.exists():
            return self._create_empty_chart()
        
        with open(progress_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        tasks = data.get('tasks', [])
        if not tasks:
            return self._create_empty_chart()
        
        # تنظیمات نمودار
        width = 800
        row_height = 40
        header_height = 60
        height = header_height + (len(tasks) * row_height) + 40
        
        svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">
  <style>
    .title {{ font-family: Arial, sans-serif; font-size: 18px; font-weight: bold; fill: #2c3e50; }}
    .task-name {{ font-family: Arial, sans-serif; font-size: 12px; fill: #2c3e50; }}
    .progress-text {{ font-family: Arial, sans-serif; font-size: 10px; fill: white; }}
    .grid-line {{ stroke: #ecf0f1; stroke-width: 1; }}
  </style>
  
  <!-- عنوان -->
  <text x="400" y="30" class="title" text-anchor="middle">نمودار گانت - {app_name.replace('_', ' ').title()}</text>
  
  <!-- خطوط شبکه -->
'''
        
        # رسم خطوط افقی
        for i in range(len(tasks) + 1):
            y = header_height + (i * row_height)
            svg += f'  <line x1="150" y1="{y}" x2="750" y2="{y}" class="grid-line"/>\n'
        
        # رسم خطوط عمودی (هر 10%)
        for i in range(11):
            x = 150 + (i * 60)
            svg += f'  <line x1="{x}" y1="{header_height}" x2="{x}" y2="{height - 40}" class="grid-line"/>\n'
            svg += f'  <text x="{x}" y="{header_height - 5}" class="task-name" text-anchor="middle">{i * 10}%</text>\n'
        
        # رسم تسک‌ها
        status_colors = {
            'completed': '#27ae60',
            'in_progress': '#3498db',
            'not_started': '#95a5a6',
            'blocked': '#e74c3c',
            'cancelled': '#e67e22'
        }
        
        for i, task in enumerate(tasks):
            y = header_height + (i * row_height) + 10
            progress = task.get('progress', 0)
            status = task.get('status', 'not_started')
            
            # نام تسک
            svg += f'  <text x="140" y="{y + 15}" class="task-name" text-anchor="end">{task["name"]}</text>\n'
            
            # نوار پیشرفت
            bar_width = (progress / 100) * 600
            color = status_colors.get(status, '#95a5a6')
            
            # پس‌زمینه
            svg += f'  <rect x="150" y="{y}" width="600" height="20" fill="#ecf0f1" rx="3"/>\n'
            
            # پیشرفت
            if bar_width > 0:
                svg += f'  <rect x="150" y="{y}" width="{bar_width}" height="20" fill="{color}" rx="3"/>\n'
                
                # درصد
                if progress > 5:
                    text_x = 150 + (bar_width / 2)
                    svg += f'  <text x="{text_x}" y="{y + 14}" class="progress-text" text-anchor="middle">{progress}%</text>\n'
        
        svg += '</svg>'
        return svg
    
    def generate_burndown_chart(self, app_name: str) -> str:
        """
        تولید نمودار Burndown
        
        Args:
            app_name: نام اپلیکیشن
            
        Returns:
            محتوای فایل SVG
        """
        # این متد می‌تواند در آینده پیاده‌سازی شود
        # برای نمایش روند کاهش تسک‌های باقیمانده در طول زمان
        pass
    
    def save_all_charts(self, app_name: str):
        """ذخیره تمام نمودارها برای یک اپلیکیشن"""
        # نمودار دونات
        self.generate_doughnut_chart(app_name)
        
        # نمودار گانت
        gantt_svg = self.generate_gantt_chart(app_name)
        gantt_path = self.base_path / "apps" / app_name / "charts" / "gantt_chart.svg"
        gantt_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(gantt_path, 'w', encoding='utf-8') as f:
            f.write(gantt_svg)


# نمونه استفاده
if __name__ == "__main__":
    generator = ChartGenerator()
    
    # تولید نمودارها برای patient_chatbot
    generator.save_all_charts("patient_chatbot")
    
    print("نمودارها با موفقیت ایجاد شدند")