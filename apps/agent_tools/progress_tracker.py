"""
Progress Tracker for Agents
"""

import json
import datetime
from pathlib import Path
from typing import Dict, List, Optional
from dataclasses import dataclass, asdict
from enum import Enum


class TaskStatus(Enum):
    """وضعیت‌های تسک"""
    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    BLOCKED = "blocked"
    CANCELLED = "cancelled"


@dataclass
class Task:
    """مدل تسک"""
    id: str
    name: str
    description: str
    status: TaskStatus
    progress: int  # 0-100
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    dependencies: List[str] = None
    notes: str = ""


class ProgressTracker:
    """
    کلاس ردیابی پیشرفت توسعه اپلیکیشن‌ها
    """
    
    def __init__(self, app_name: str, base_path: str = "/workspace/unified_agent"):
        self.app_name = app_name
        self.base_path = Path(base_path)
        self.app_path = self.base_path / "apps" / app_name
        self.progress_file = self.app_path / "PROGRESS.json"
        self.log_file = self.app_path / "LOG.md"
        self.tasks: Dict[str, Task] = {}
        self._load_progress()
        
    def _load_progress(self):
        """بارگذاری فایل پیشرفت"""
        if self.progress_file.exists():
            with open(self.progress_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                for task_data in data.get('tasks', []):
                    task = Task(
                        id=task_data['id'],
                        name=task_data['name'],
                        description=task_data['description'],
                        status=TaskStatus(task_data['status']),
                        progress=task_data['progress'],
                        started_at=task_data.get('started_at'),
                        completed_at=task_data.get('completed_at'),
                        dependencies=task_data.get('dependencies', []),
                        notes=task_data.get('notes', '')
                    )
                    self.tasks[task.id] = task
    
    def _save_progress(self):
        """ذخیره فایل پیشرفت"""
        data = {
            'app_name': self.app_name,
            'last_updated': datetime.datetime.now().isoformat(),
            'overall_progress': self.calculate_overall_progress(),
            'tasks': [asdict(task) for task in self.tasks.values()]
        }
        
        # تبدیل TaskStatus به string
        for task_data in data['tasks']:
            task_data['status'] = task_data['status'].value
        
        with open(self.progress_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    
    def add_task(self, task_id: str, name: str, description: str,
                 dependencies: List[str] = None) -> Task:
        """افزودن تسک جدید"""
        task = Task(
            id=task_id,
            name=name,
            description=description,
            status=TaskStatus.NOT_STARTED,
            progress=0,
            dependencies=dependencies or []
        )
        self.tasks[task_id] = task
        self._save_progress()
        self._log_action(f"تسک جدید اضافه شد: {name}")
        return task
    
    def start_task(self, task_id: str) -> bool:
        """شروع تسک"""
        if task_id not in self.tasks:
            return False
        
        task = self.tasks[task_id]
        
        # بررسی dependencies
        if not self._check_dependencies(task):
            task.status = TaskStatus.BLOCKED
            self._save_progress()
            self._log_action(f"تسک {task.name} به دلیل وابستگی‌ها مسدود شد")
            return False
        
        task.status = TaskStatus.IN_PROGRESS
        task.started_at = datetime.datetime.now().isoformat()
        self._save_progress()
        self._log_action(f"تسک {task.name} شروع شد")
        return True
    
    def update_task_progress(self, task_id: str, progress: int, notes: str = ""):
        """به‌روزرسانی پیشرفت تسک"""
        if task_id not in self.tasks:
            return
        
        task = self.tasks[task_id]
        task.progress = min(100, max(0, progress))
        if notes:
            task.notes = notes
        
        # اگر 100% شد، تکمیل کن
        if task.progress == 100 and task.status != TaskStatus.COMPLETED:
            self.complete_task(task_id)
        else:
            self._save_progress()
            self._log_action(f"تسک {task.name} به {progress}% رسید")
    
    def complete_task(self, task_id: str) -> bool:
        """تکمیل تسک"""
        if task_id not in self.tasks:
            return False
        
        task = self.tasks[task_id]
        task.status = TaskStatus.COMPLETED
        task.progress = 100
        task.completed_at = datetime.datetime.now().isoformat()
        self._save_progress()
        self._log_action(f"تسک {task.name} تکمیل شد")
        
        # بررسی unblock کردن تسک‌های وابسته
        self._check_unblock_tasks()
        return True
    
    def cancel_task(self, task_id: str, reason: str = ""):
        """لغو تسک"""
        if task_id not in self.tasks:
            return
        
        task = self.tasks[task_id]
        task.status = TaskStatus.CANCELLED
        task.notes = f"لغو شد: {reason}" if reason else "لغو شد"
        self._save_progress()
        self._log_action(f"تسک {task.name} لغو شد: {reason}")
    
    def _check_dependencies(self, task: Task) -> bool:
        """بررسی تکمیل وابستگی‌ها"""
        for dep_id in task.dependencies:
            if dep_id in self.tasks:
                dep_task = self.tasks[dep_id]
                if dep_task.status != TaskStatus.COMPLETED:
                    return False
        return True
    
    def _check_unblock_tasks(self):
        """بررسی و unblock کردن تسک‌های مسدود"""
        for task in self.tasks.values():
            if task.status == TaskStatus.BLOCKED:
                if self._check_dependencies(task):
                    task.status = TaskStatus.NOT_STARTED
                    self._log_action(f"تسک {task.name} از حالت مسدود خارج شد")
        self._save_progress()
    
    def calculate_overall_progress(self) -> int:
        """محاسبه پیشرفت کلی"""
        if not self.tasks:
            return 0
        
        total_progress = sum(task.progress for task in self.tasks.values())
        return int(total_progress / len(self.tasks))
    
    def get_status_summary(self) -> Dict[str, int]:
        """خلاصه وضعیت تسک‌ها"""
        summary = {
            TaskStatus.NOT_STARTED.value: 0,
            TaskStatus.IN_PROGRESS.value: 0,
            TaskStatus.COMPLETED.value: 0,
            TaskStatus.BLOCKED.value: 0,
            TaskStatus.CANCELLED.value: 0
        }
        
        for task in self.tasks.values():
            summary[task.status.value] += 1
        
        return summary
    
    def get_active_tasks(self) -> List[Task]:
        """دریافت تسک‌های فعال"""
        return [
            task for task in self.tasks.values()
            if task.status == TaskStatus.IN_PROGRESS
        ]
    
    def get_blocked_tasks(self) -> List[Task]:
        """دریافت تسک‌های مسدود"""
        return [
            task for task in self.tasks.values()
            if task.status == TaskStatus.BLOCKED
        ]
    
    def _log_action(self, message: str):
        """ثبت لاگ اقدامات"""
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_entry = f"\n### {timestamp}\n{message}\n"
        
        if self.log_file.exists():
            with open(self.log_file, 'a', encoding='utf-8') as f:
                f.write(log_entry)
        else:
            with open(self.log_file, 'w', encoding='utf-8') as f:
                f.write(f"# لاگ توسعه {self.app_name}\n")
                f.write(log_entry)
    
    def generate_progress_report(self) -> str:
        """تولید گزارش پیشرفت"""
        overall_progress = self.calculate_overall_progress()
        status_summary = self.get_status_summary()
        
        report = f"""# گزارش پیشرفت {self.app_name}

## پیشرفت کلی: {overall_progress}%

### وضعیت تسک‌ها:
- ✅ تکمیل شده: {status_summary[TaskStatus.COMPLETED.value]}
- 🔄 در حال انجام: {status_summary[TaskStatus.IN_PROGRESS.value]}
- ⏸️ شروع نشده: {status_summary[TaskStatus.NOT_STARTED.value]}
- 🚫 مسدود: {status_summary[TaskStatus.BLOCKED.value]}
- ❌ لغو شده: {status_summary[TaskStatus.CANCELLED.value]}

### جزئیات تسک‌ها:
"""
        
        # مرتب‌سازی بر اساس وضعیت
        sorted_tasks = sorted(
            self.tasks.values(),
            key=lambda t: (t.status.value, -t.progress)
        )
        
        for task in sorted_tasks:
            status_icon = {
                TaskStatus.COMPLETED: "✅",
                TaskStatus.IN_PROGRESS: "🔄",
                TaskStatus.NOT_STARTED: "⏸️",
                TaskStatus.BLOCKED: "🚫",
                TaskStatus.CANCELLED: "❌"
            }[task.status]
            
            report += f"\n#### {status_icon} {task.name}\n"
            report += f"- **شناسه**: {task.id}\n"
            report += f"- **توضیحات**: {task.description}\n"
            report += f"- **پیشرفت**: {task.progress}%\n"
            
            if task.dependencies:
                report += f"- **وابستگی‌ها**: {', '.join(task.dependencies)}\n"
            
            if task.started_at:
                report += f"- **شروع**: {task.started_at}\n"
            
            if task.completed_at:
                report += f"- **پایان**: {task.completed_at}\n"
            
            if task.notes:
                report += f"- **یادداشت**: {task.notes}\n"
        
        # تسک‌های فعال
        active_tasks = self.get_active_tasks()
        if active_tasks:
            report += "\n### تسک‌های فعال:\n"
            for task in active_tasks:
                report += f"- {task.name} ({task.progress}%)\n"
        
        # تسک‌های مسدود
        blocked_tasks = self.get_blocked_tasks()
        if blocked_tasks:
            report += "\n### تسک‌های مسدود:\n"
            for task in blocked_tasks:
                deps = ", ".join(task.dependencies)
                report += f"- {task.name} (منتظر: {deps})\n"
        
        return report
    
    def initialize_default_tasks(self):
        """ایجاد تسک‌های پیش‌فرض برای اپلیکیشن"""
        default_tasks = [
            ("planning", "برنامه‌ریزی و طراحی", "تکمیل PLAN.md و طراحی API", []),
            ("models", "پیاده‌سازی مدل‌ها", "ایجاد مدل‌های دیتابیس", ["planning"]),
            ("four_cores", "پیاده‌سازی چهار هسته", "پیاده‌سازی معماری چهار هسته‌ای", ["planning"]),
            ("views", "پیاده‌سازی Views", "ایجاد API endpoints", ["models", "four_cores"]),
            ("serializers", "پیاده‌سازی Serializers", "ایجاد serializers", ["models"]),
            ("integrations", "یکپارچه‌سازی", "ادغام با unified services", ["views"]),
            ("tests", "نوشتن تست‌ها", "ایجاد unit و integration tests", ["views", "serializers"]),
            ("documentation", "مستندسازی", "تکمیل README و API docs", ["tests"]),
            ("deployment", "آماده‌سازی deployment", "ایجاد فایل‌های deployment", ["documentation"]),
        ]
        
        for task_id, name, description, dependencies in default_tasks:
            self.add_task(task_id, name, description, dependencies)


# نمونه استفاده
if __name__ == "__main__":
    # ایجاد tracker برای patient_chatbot
    tracker = ProgressTracker("patient_chatbot")
    
    # ایجاد تسک‌های پیش‌فرض
    tracker.initialize_default_tasks()
    
    # شروع تسک planning
    tracker.start_task("planning")
    tracker.update_task_progress("planning", 50, "PLAN.md نیمه کامل شد")
    tracker.complete_task("planning")
    
    # شروع تسک models
    tracker.start_task("models")
    tracker.update_task_progress("models", 30)
    
    # تولید گزارش
    report = tracker.generate_progress_report()
    print(report)