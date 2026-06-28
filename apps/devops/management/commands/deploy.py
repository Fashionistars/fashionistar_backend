"""
Management command برای deployment
"""
from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth.models import User
from devops.services.deployment_service import DeploymentService
from devops.models import EnvironmentConfig
import sys


class Command(BaseCommand):
    """
    دستور deployment از طریق CLI
    
    استفاده:
    python manage.py deploy --environment production --version v1.2.3
    python manage.py deploy -e staging -v v1.2.3 --branch develop --no-migrations
    """
    
    help = 'اجرای deployment برای محیط مشخص'
    
    def add_arguments(self, parser):
        """تعریف آرگومان‌های command"""
        parser.add_argument(
            '-e', '--environment',
            type=str,
            required=True,
            help='نام محیط برای deployment (مثل production, staging)'
        )
        
        parser.add_argument(
            '-v', '--version',
            type=str,
            required=True,
            help='نسخه برای deployment'
        )
        
        parser.add_argument(
            '-b', '--branch',
            type=str,
            default='main',
            help='شاخه git (پیش‌فرض: main)'
        )
        
        parser.add_argument(
            '--no-build',
            action='store_true',
            help='عدم ساخت مجدد Docker images'
        )
        
        parser.add_argument(
            '--no-migrations',
            action='store_true',
            help='عدم اجرای migration ها'
        )
        
        parser.add_argument(
            '--no-restart',
            action='store_true',
            help='عدم راه‌اندازی مجدد سرویس‌ها'
        )
        
        parser.add_argument(
            '--user',
            type=str,
            help='نام کاربری اجراکننده deployment'
        )
        
        parser.add_argument(
            '--force',
            action='store_true',
            help='اجرای اجباری بدون تایید'
        )
    
    def handle(self, *args, **options):
        """اجرای command"""
        environment_name = options['environment']
        version = options['version']
        branch = options['branch']
        build_images = not options['no_build']
        run_migrations = not options['no_migrations']
        restart_services = not options['no_restart']
        force = options['force']
        
        try:
            # بررسی وجود محیط
            environment = EnvironmentConfig.objects.get(
                name=environment_name,
                is_active=True
            )
        except EnvironmentConfig.DoesNotExist:
            raise CommandError(f'محیط {environment_name} یافت نشد یا غیرفعال است')
        
        # یافتن کاربر
        user = None
        if options['user']:
            try:
                user = User.objects.get(username=options['user'])
            except User.DoesNotExist:
                self.stdout.write(
                    self.style.WARNING(f'کاربر {options["user"]} یافت نشد. deployment به عنوان system اجرا می‌شود.')
                )
        
        # نمایش اطلاعات deployment
        self.stdout.write(self.style.SUCCESS('\n=== اطلاعات Deployment ==='))
        self.stdout.write(f'محیط: {environment_name}')
        self.stdout.write(f'نسخه: {version}')
        self.stdout.write(f'شاخه: {branch}')
        self.stdout.write(f'ساخت Images: {"بله" if build_images else "خیر"}')
        self.stdout.write(f'اجرای Migrations: {"بله" if run_migrations else "خیر"}')
        self.stdout.write(f'راه‌اندازی مجدد: {"بله" if restart_services else "خیر"}')
        if user:
            self.stdout.write(f'کاربر: {user.username}')
        self.stdout.write('=' * 25)
        
        # تایید اجرا
        if not force:
            confirm = input('\nآیا مطمئن هستید که می‌خواهید deployment را اجرا کنید؟ (y/N): ')
            if confirm.lower() not in ['y', 'yes']:
                self.stdout.write(self.style.WARNING('Deployment لغو شد.'))
                return
        
        try:
            # ایجاد سرویس deployment
            deployment_service = DeploymentService(environment_name)
            
            self.stdout.write(self.style.SUCCESS(f'\n🚀 شروع deployment نسخه {version}...'))
            
            # اجرای deployment
            deployment = deployment_service.deploy(
                version=version,
                branch=branch,
                user=user,
                build_images=build_images,
                run_migrations=run_migrations,
                restart_services=restart_services
            )
            
            # نمایش نتیجه
            if deployment.status == 'success':
                self.stdout.write(
                    self.style.SUCCESS('\n✅ Deployment با موفقیت تکمیل شد!')
                )
                self.stdout.write(f'شناسه Deployment: {deployment.id}')
                if deployment.duration:
                    self.stdout.write(f'مدت زمان: {deployment.duration.total_seconds():.0f} ثانیه')
            else:
                self.stdout.write(
                    self.style.ERROR('\n❌ Deployment ناموفق بود!')
                )
                self.stdout.write(f'وضعیت: {deployment.get_status_display()}')
                
                # نمایش لاگ‌های خطا
                if deployment.deployment_logs:
                    self.stdout.write('\n--- لاگ‌های Deployment ---')
                    self.stdout.write(deployment.deployment_logs[-1000:])  # آخرین 1000 کاراکتر
                
                sys.exit(1)
                
        except Exception as e:
            raise CommandError(f'خطا در deployment: {str(e)}')
        
        self.stdout.write(self.style.SUCCESS('\n🎉 Deployment با موفقیت انجام شد!'))


class RollbackCommand(BaseCommand):
    """
    دستور rollback deployment
    
    استفاده:
    python manage.py rollback --environment production --target-deployment-id abc-123
    """
    
    help = 'rollback به deployment قبلی'
    
    def add_arguments(self, parser):
        """تعریف آرگومان‌های command"""
        parser.add_argument(
            '-e', '--environment',
            type=str,
            required=True,
            help='نام محیط'
        )
        
        parser.add_argument(
            '-t', '--target-deployment-id',
            type=str,
            required=True,
            help='شناسه deployment مقصد'
        )
        
        parser.add_argument(
            '--user',
            type=str,
            help='نام کاربری اجراکننده rollback'
        )
        
        parser.add_argument(
            '--force',
            action='store_true',
            help='اجرای اجباری بدون تایید'
        )
    
    def handle(self, *args, **options):
        """اجرای rollback command"""
        environment_name = options['environment']
        target_deployment_id = options['target_deployment_id']
        force = options['force']
        
        try:
            # بررسی وجود محیط
            environment = EnvironmentConfig.objects.get(
                name=environment_name,
                is_active=True
            )
        except EnvironmentConfig.DoesNotExist:
            raise CommandError(f'محیط {environment_name} یافت نشد')
        
        # یافتن کاربر
        user = None
        if options['user']:
            try:
                user = User.objects.get(username=options['user'])
            except User.DoesNotExist:
                self.stdout.write(
                    self.style.WARNING(f'کاربر {options["user"]} یافت نشد.')
                )
        
        # نمایش اطلاعات
        self.stdout.write(self.style.WARNING('\n=== اطلاعات Rollback ==='))
        self.stdout.write(f'محیط: {environment_name}')
        self.stdout.write(f'Target Deployment ID: {target_deployment_id}')
        if user:
            self.stdout.write(f'کاربر: {user.username}')
        self.stdout.write('=' * 23)
        
        # تایید اجرا
        if not force:
            confirm = input('\nآیا مطمئن هستید که می‌خواهید rollback را اجرا کنید؟ (y/N): ')
            if confirm.lower() not in ['y', 'yes']:
                self.stdout.write(self.style.WARNING('Rollback لغو شد.'))
                return
        
        try:
            # ایجاد سرویس deployment
            deployment_service = DeploymentService(environment_name)
            
            self.stdout.write(self.style.WARNING('\n🔄 شروع rollback...'))
            
            # اجرای rollback
            rollback_deployment = deployment_service.rollback(
                target_deployment_id=target_deployment_id,
                user=user
            )
            
            # نمایش نتیجه
            if rollback_deployment.status == 'success':
                self.stdout.write(
                    self.style.SUCCESS('\n✅ Rollback با موفقیت تکمیل شد!')
                )
                self.stdout.write(f'شناسه Rollback: {rollback_deployment.id}')
                if rollback_deployment.duration:
                    self.stdout.write(f'مدت زمان: {rollback_deployment.duration.total_seconds():.0f} ثانیه')
            else:
                self.stdout.write(
                    self.style.ERROR('\n❌ Rollback ناموفق بود!')
                )
                self.stdout.write(f'وضعیت: {rollback_deployment.get_status_display()}')
                
                # نمایش لاگ‌های خطا
                if rollback_deployment.deployment_logs:
                    self.stdout.write('\n--- لاگ‌های Rollback ---')
                    self.stdout.write(rollback_deployment.deployment_logs[-1000:])
                
                sys.exit(1)
                
        except ValueError as e:
            raise CommandError(f'خطا در rollback: {str(e)}')
        except Exception as e:
            raise CommandError(f'خطای غیرمنتظره: {str(e)}')
        
        self.stdout.write(self.style.SUCCESS('\n🎉 Rollback با موفقیت انجام شد!'))