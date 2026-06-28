"""
Structure Validator for Agents
"""

import os
import json
import ast
from pathlib import Path
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass


@dataclass
class ValidationResult:
    """نتیجه اعتبارسنجی"""
    is_valid: bool
    errors: List[str]
    warnings: List[str]
    info: Dict[str, any]


class StructureValidator:
    """
    کلاس اعتبارسنجی ساختار اپلیکیشن‌ها
    """
    
    def __init__(self, base_path: str = "/workspace/unified_agent"):
        self.base_path = Path(base_path)
        self.checklist_path = self.base_path / "FINAL_CHECKLIST.json"
        self._load_checklist()
        
    def _load_checklist(self):
        """بارگذاری چک‌لیست نهایی"""
        with open(self.checklist_path, 'r', encoding='utf-8') as f:
            self.checklist = json.load(f)
    
    def validate_app_structure(self, app_name: str) -> ValidationResult:
        """
        اعتبارسنجی کامل ساختار یک اپلیکیشن
        
        Args:
            app_name: نام اپلیکیشن
            
        Returns:
            ValidationResult object
        """
        app_path = self.base_path / "apps" / app_name
        errors = []
        warnings = []
        info = {
            'app_name': app_name,
            'app_path': str(app_path),
            'checks_passed': 0,
            'checks_failed': 0
        }
        
        # بررسی وجود پوشه اپ
        if not app_path.exists():
            errors.append(f"پوشه اپلیکیشن {app_name} وجود ندارد")
            return ValidationResult(False, errors, warnings, info)
        
        # بررسی فایل‌های اجباری
        self._check_required_files(app_path, errors, warnings, info)
        
        # بررسی ساختار پوشه‌ها
        self._check_directory_structure(app_path, errors, warnings, info)
        
        # بررسی محتوای فایل‌ها
        self._check_file_contents(app_path, errors, warnings, info)
        
        # بررسی معماری چهار هسته‌ای
        self._check_four_cores(app_path, errors, warnings, info)
        
        # بررسی امنیت
        self._check_security(app_path, errors, warnings, info)
        
        # بررسی imports
        self._check_imports(app_path, errors, warnings, info)
        
        is_valid = len(errors) == 0
        return ValidationResult(is_valid, errors, warnings, info)
    
    def _check_required_files(self, app_path: Path, errors: List[str], 
                            warnings: List[str], info: Dict):
        """بررسی فایل‌های اجباری"""
        required_files = [
            "PLAN.md",
            "CHECKLIST.json",
            "PROGRESS.json",
            "README.md",
            "app_code/__init__.py",
            "app_code/apps.py",
            "app_code/models.py",
            "app_code/views.py",
            "app_code/serializers.py",
            "app_code/urls.py",
            "app_code/cores/api_ingress.py",
            "app_code/cores/orchestrator.py",
        ]
        
        for file_path in required_files:
            full_path = app_path / file_path
            if not full_path.exists():
                errors.append(f"فایل اجباری {file_path} وجود ندارد")
                info['checks_failed'] += 1
            else:
                info['checks_passed'] += 1
    
    def _check_directory_structure(self, app_path: Path, errors: List[str],
                                 warnings: List[str], info: Dict):
        """بررسی ساختار پوشه‌ها"""
        required_dirs = [
            "app_code",
            "app_code/cores",
            "app_code/services",
            "app_code/migrations",
            "app_code/tests",
            "deployment",
            "docs",
        ]
        
        for dir_path in required_dirs:
            full_path = app_path / dir_path
            if not full_path.is_dir():
                errors.append(f"پوشه اجباری {dir_path} وجود ندارد")
                info['checks_failed'] += 1
            else:
                info['checks_passed'] += 1
    
    def _check_file_contents(self, app_path: Path, errors: List[str],
                           warnings: List[str], info: Dict):
        """بررسی محتوای فایل‌ها"""
        
        # بررسی models.py
        models_path = app_path / "app_code" / "models.py"
        if models_path.exists():
            with open(models_path, 'r', encoding='utf-8') as f:
                content = f.read()
                
                # بررسی عدم وجود User model جدید
                if 'class User(' in content or 'class CustomUser(' in content:
                    errors.append("ایجاد User model جدید ممنوع است")
                    info['checks_failed'] += 1
                
                # بررسی import صحیح
                if 'from django.contrib.auth import get_user_model' not in content:
                    warnings.append("models.py باید از get_user_model استفاده کند")
                
                if 'from app_standards.models.base_models import BaseModel' not in content:
                    warnings.append("models.py باید از BaseModel استفاده کند")
        
        # بررسی views.py
        views_path = app_path / "app_code" / "views.py"
        if views_path.exists():
            with open(views_path, 'r', encoding='utf-8') as f:
                content = f.read()
                
                if 'from app_standards.four_cores import' not in content:
                    warnings.append("views.py باید از four_cores استفاده کند")
    
    def _check_four_cores(self, app_path: Path, errors: List[str],
                        warnings: List[str], info: Dict):
        """بررسی پیاده‌سازی چهار هسته"""
        cores = [
            "api_ingress.py",
            "text_processor.py",
            "speech_processor.py",
            "orchestrator.py"
        ]
        
        cores_path = app_path / "app_code" / "cores"
        implemented_cores = 0
        
        for core in cores:
            core_path = cores_path / core
            if core_path.exists():
                implemented_cores += 1
                
                # بررسی import از app_standards
                with open(core_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                    if 'from app_standards.four_cores import' not in content:
                        warnings.append(f"{core} باید از app_standards.four_cores import کند")
        
        if implemented_cores < 2:
            errors.append("حداقل دو هسته باید پیاده‌سازی شوند (API Ingress و Orchestrator)")
            info['checks_failed'] += 1
        else:
            info['checks_passed'] += 1
        
        info['implemented_cores'] = implemented_cores
    
    def _check_security(self, app_path: Path, errors: List[str],
                      warnings: List[str], info: Dict):
        """بررسی رعایت سیاست‌های امنیتی"""
        
        # بررسی permissions
        permissions_path = app_path / "app_code" / "permissions.py"
        if permissions_path.exists():
            info['has_custom_permissions'] = True
        else:
            warnings.append("فایل permissions.py یافت نشد")
        
        # بررسی authentication در views
        views_path = app_path / "app_code" / "views.py"
        if views_path.exists():
            with open(views_path, 'r', encoding='utf-8') as f:
                content = f.read()
                
                if '@permission_classes' not in content:
                    warnings.append("هیچ permission_class در views تعریف نشده")
                
                if 'IsAuthenticated' not in content:
                    warnings.append("IsAuthenticated استفاده نشده است")
    
    def _check_imports(self, app_path: Path, errors: List[str],
                     warnings: List[str], info: Dict):
        """بررسی import های اجباری"""
        must_import = self.checklist.get('validation_rules', {}).get('must_import', {})
        
        for file_name, required_imports in must_import.items():
            file_path = app_path / "app_code" / file_name
            if file_path.exists():
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                    
                for required_import in required_imports:
                        if required_import not in content:
                            warnings.append(f"{file_name} باید شامل '{required_import}' باشد")
    
    def validate_code_quality(self, app_path: Path) -> Dict[str, any]:
        """بررسی کیفیت کد"""
        quality_info = {
            'total_files': 0,
            'python_files': 0,
            'total_lines': 0,
            'docstring_count': 0,
            'comment_lines': 0,
            'test_files': 0,
            'has_readme': False,
            'has_api_spec': False
        }
        
        # شمارش فایل‌ها و خطوط
        for root, dirs, files in os.walk(app_path):
            for file in files:
                quality_info['total_files'] += 1
                
                if file.endswith('.py'):
                    quality_info['python_files'] += 1
                    file_path = Path(root) / file
                    
                    if 'test_' in file:
                        quality_info['test_files'] += 1
                    
                    with open(file_path, 'r', encoding='utf-8') as f:
                        lines = f.readlines()
                        quality_info['total_lines'] += len(lines)
                        
                        for line in lines:
                            if line.strip().startswith('#'):
                                quality_info['comment_lines'] += 1
                        
                        # شمارش docstring
                        content = ''.join(lines)
                        quality_info['docstring_count'] += content.count('"""')
        
        # بررسی فایل‌های مستندات
        if (app_path / "README.md").exists():
            quality_info['has_readme'] = True
        
        if (app_path / "docs" / "api_spec.yaml").exists():
            quality_info['has_api_spec'] = True
        
        return quality_info
    
    def generate_validation_report(self, app_name: str) -> str:
        """تولید گزارش اعتبارسنجی"""
        result = self.validate_app_structure(app_name)
        quality = self.validate_code_quality(self.base_path / "apps" / app_name)
        
        report = f"""
# گزارش اعتبارسنجی اپلیکیشن {app_name}

## نتیجه کلی: {'✅ معتبر' if result.is_valid else '❌ نامعتبر'}

### آمار بررسی:
- تست‌های موفق: {result.info['checks_passed']}
- تست‌های ناموفق: {result.info['checks_failed']}
- هسته‌های پیاده‌سازی شده: {result.info.get('implemented_cores', 0)}/4

### خطاها ({len(result.errors)}):
"""
        
        for error in result.errors:
            report += f"- ❌ {error}\n"
        
        report += f"\n### هشدارها ({len(result.warnings)}):\n"
        for warning in result.warnings:
            report += f"- ⚠️ {warning}\n"
        
        report += f"""
### کیفیت کد:
- تعداد فایل‌های Python: {quality['python_files']}
- تعداد خطوط کد: {quality['total_lines']}
- تعداد Docstring: {quality['docstring_count']}
- تعداد فایل‌های تست: {quality['test_files']}
- README: {'✅' if quality['has_readme'] else '❌'}
- API Spec: {'✅' if quality['has_api_spec'] else '❌'}

### توصیه‌ها:
"""
        
        if not result.is_valid:
            report += "- ابتدا خطاهای بحرانی را رفع کنید\n"
        
        if len(result.warnings) > 5:
            report += "- هشدارها را بررسی و رفع کنید\n"
        
        if quality['test_files'] < 4:
            report += "- تست‌های بیشتری بنویسید\n"
        
        if quality['docstring_count'] < quality['python_files'] * 2:
            report += "- Docstring برای توابع و کلاس‌ها اضافه کنید\n"
        
        return report


# نمونه استفاده
if __name__ == "__main__":
    validator = StructureValidator()
    
    # اعتبارسنجی patient_chatbot
    result = validator.validate_app_structure("patient_chatbot")
    
    if result.is_valid:
        print("✅ ساختار اپلیکیشن معتبر است")
    else:
        print("❌ ساختار اپلیکیشن نامعتبر است")
        print("\nخطاها:")
        for error in result.errors:
            print(f"  - {error}")
    
    # تولید گزارش کامل
    report = validator.generate_validation_report("patient_chatbot")
    print(report)