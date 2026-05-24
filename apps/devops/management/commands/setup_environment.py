"""
Management command برای راه‌اندازی اولیه محیط
"""
from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth.models import User
from devops.models import EnvironmentConfig, ServiceMonitoring
import json


class Command(BaseCommand):
    """
    دستور راه‌اندازی اولیه محیط DevOps
    
    استفاده:
    python manage.py setup_environment --config environments.json
    python manage.py setup_environment --environment production --quick-setup
    """
    
    help = 'راه‌اندازی اولیه محیط‌ها و سرویس‌های مانیتورینگ'
    
    def add_arguments(self, parser):
        """تعریف آرگومان‌های command"""
        parser.add_argument(
            '--config',
            type=str,
            help='مسیر فایل JSON تنظیمات'
        )
        
        parser.add_argument(
            '-e', '--environment',
            type=str,
            help='نام محیط برای راه‌اندازی سریع'
        )
        
        parser.add_argument(
            '--type',
            type=str,
            choices=['development', 'staging', 'production', 'testing'],
            default='development',
            help='نوع محیط'
        )
        
        parser.add_argument(
            '--quick-setup',
            action='store_true',
            help='راه‌اندازی سریع با تنظیمات پیش‌فرض'
        )
        
        parser.add_argument(
            '--force',
            action='store_true',
            help='بازنویسی محیط‌های موجود'
        )
    
    def handle(self, *args, **options):
        """اجرای command"""
        config_file = options.get('config')
        environment_name = options.get('environment')
        environment_type = options.get('type')
        quick_setup = options.get('quick_setup')
        force = options.get('force')
        
        try:
            if config_file:
                # راه‌اندازی از فایل JSON
                self._setup_from_config(config_file, force)
            elif environment_name and quick_setup:
                # راه‌اندازی سریع
                self._quick_setup(environment_name, environment_type, force)
            else:
                # راه‌اندازی تعاملی
                self._interactive_setup(force)
                
        except Exception as e:
            raise CommandError(f'خطا در راه‌اندازی: {str(e)}')
        
        self.stdout.write(self.style.SUCCESS('\n🎉 راه‌اندازی با موفقیت انجام شد!'))
    
    def _setup_from_config(self, config_file, force):
        """راه‌اندازی از فایل تنظیمات"""
        try:
            with open(config_file, 'r', encoding='utf-8') as f:
                config = json.load(f)
        except FileNotFoundError:
            raise CommandError(f'فایل {config_file} یافت نشد')
        except json.JSONDecodeError:
            raise CommandError(f'فایل {config_file} فرمت JSON معتبر ندارد')
        
        self.stdout.write(f"📁 بارگذاری تنظیمات از {config_file}")
        
        # راه‌اندازی محیط‌ها
        environments = config.get('environments', [])
        for env_config in environments:
            self._create_environment(env_config, force)
        
        # راه‌اندازی سرویس‌های مانیتورینگ
        monitoring = config.get('monitoring', [])
        for monitor_config in monitoring:
            self._create_monitoring_service(monitor_config, force)
    
    def _quick_setup(self, environment_name, environment_type, force):
        """راه‌اندازی سریع با تنظیمات پیش‌فرض"""
        self.stdout.write(f"⚡ راه‌اندازی سریع محیط {environment_name}")
        
        # ایجاد محیط
        env_config = {
            'name': environment_name,
            'environment_type': environment_type,
            'description': f'محیط {environment_type} ایجاد شده با setup سریع'
        }
        
        environment = self._create_environment(env_config, force)
        
        # سرویس‌های پیش‌فرض
        default_services = self._get_default_services(environment_name, environment_type)
        
        for service_config in default_services:
            service_config['environment'] = environment
            self._create_monitoring_service(service_config, force)
    
    def _interactive_setup(self, force):
        """راه‌اندازی تعاملی"""
        self.stdout.write("🔧 راه‌اندازی تعاملی محیط")
        
        # درخواست اطلاعات محیط
        environment_name = input("نام محیط: ")
        if not environment_name:
            raise CommandError("نام محیط الزامی است")
        
        print("\nنوع محیط:")
        print("1. Development")
        print("2. Staging") 
        print("3. Production")
        print("4. Testing")
        
        choice = input("انتخاب کنید (1-4): ")
        type_mapping = {
            '1': 'development',
            '2': 'staging',
            '3': 'production',
            '4': 'testing'
        }
        
        environment_type = type_mapping.get(choice, 'development')
        description = input("توضیحات (اختیاری): ")
        
        # ایجاد محیط
        env_config = {
            'name': environment_name,
            'environment_type': environment_type,
            'description': description
        }
        
        environment = self._create_environment(env_config, force)
        
        # سوال برای سرویس‌های مانیتورینگ
        add_monitoring = input("\nآیا می‌خواهید سرویس‌های مانیتورینگ پیش‌فرض اضافه شوند؟ (y/N): ")
        
        if add_monitoring.lower() in ['y', 'yes']:
            default_services = self._get_default_services(environment_name, environment_type)
            
            for service_config in default_services:
                service_config['environment'] = environment
                self._create_monitoring_service(service_config, force)
    
    def _create_environment(self, config, force):
        """ایجاد محیط"""
        name = config['name']
        
        # بررسی وجود محیط
        existing_env = EnvironmentConfig.objects.filter(name=name).first()
        
        if existing_env and not force:
            self.stdout.write(
                self.style.WARNING(f"⚠️  محیط {name} از قبل موجود است (با --force می‌توانید بازنویسی کنید)")
            )
            return existing_env
        
        if existing_env and force:
            existing_env.delete()
            self.stdout.write(f"🗑️  محیط قبلی {name} حذف شد")
        
        # ایجاد محیط جدید
        environment = EnvironmentConfig.objects.create(
            name=config['name'],
            environment_type=config['environment_type'],
            description=config.get('description', ''),
            is_active=config.get('is_active', True)
        )
        
        self.stdout.write(
            self.style.SUCCESS(f"✅ محیط {name} ({config['environment_type']}) ایجاد شد")
        )
        
        return environment
    
    def _create_monitoring_service(self, config, force):
        """ایجاد سرویس مانیتورینگ"""
        environment = config['environment']
        service_name = config['service_name']
        
        # بررسی وجود سرویس
        existing_service = ServiceMonitoring.objects.filter(
            environment=environment,
            service_name=service_name
        ).first()
        
        if existing_service and not force:
            self.stdout.write(
                self.style.WARNING(f"⚠️  سرویس {service_name} در محیط {environment.name} از قبل موجود است")
            )
            return existing_service
        
        if existing_service and force:
            existing_service.delete()
            self.stdout.write(f"🗑️  سرویس قبلی {service_name} حذف شد")
        
        # ایجاد سرویس جدید
        service = ServiceMonitoring.objects.create(
            environment=environment,
            service_name=config['service_name'],
            service_type=config['service_type'],
            health_check_url=config['health_check_url'],
            check_interval=config.get('check_interval', 300),
            timeout=config.get('timeout', 30),
            is_active=config.get('is_active', True),
            alert_on_failure=config.get('alert_on_failure', True)
        )
        
        self.stdout.write(
            self.style.SUCCESS(f"✅ سرویس مانیتورینگ {service_name} اضافه شد")
        )
        
        return service
    
    def _get_default_services(self, environment_name, environment_type):
        """دریافت سرویس‌های پیش‌فرض بر اساس نوع محیط"""
        
        # URL های پایه بر اساس محیط
        if environment_type == 'production':
            base_url = f"https://{environment_name}.helssa.ir"
        elif environment_type == 'staging':
            base_url = f"https://{environment_name}-staging.helssa.ir"
        else:
            base_url = "http://localhost:8000"
        
        default_services = [
            {
                'service_name': 'web',
                'service_type': 'web',
                'health_check_url': f"{base_url}/health/",
                'check_interval': 300,
                'timeout': 30
            },
            {
                'service_name': 'database',
                'service_type': 'database',
                'health_check_url': f"{base_url}/health/",
                'check_interval': 600,
                'timeout': 15
            },
            {
                'service_name': 'cache',
                'service_type': 'cache',
                'health_check_url': f"{base_url}/health/",
                'check_interval': 300,
                'timeout': 10
            }
        ]
        
        # سرویس‌های اضافی برای production
        if environment_type == 'production':
            default_services.extend([
                {
                    'service_name': 'nginx',
                    'service_type': 'proxy',
                    'health_check_url': f"{base_url}/health/",
                    'check_interval': 180,
                    'timeout': 10
                },
                {
                    'service_name': 'minio',
                    'service_type': 'storage',
                    'health_check_url': f"http://minio:9000/minio/health/live",
                    'check_interval': 600,
                    'timeout': 20
                }
            ])
        
        return default_services