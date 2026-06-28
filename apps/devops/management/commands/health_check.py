"""
Management command برای health check
"""
from django.core.management.base import BaseCommand, CommandError
from devops.services.health_service import HealthService
from devops.models import EnvironmentConfig, ServiceMonitoring
import json
import sys


class Command(BaseCommand):
    """
    دستور health check از طریق CLI
    
    استفاده:
    python manage.py health_check
    python manage.py health_check --environment production
    python manage.py health_check --service web --environment production
    """
    
    help = 'اجرای health check برای سیستم یا سرویس خاص'
    
    def add_arguments(self, parser):
        """تعریف آرگومان‌های command"""
        parser.add_argument(
            '-e', '--environment',
            type=str,
            help='نام محیط برای health check'
        )
        
        parser.add_argument(
            '-s', '--service',
            type=str,
            help='نام سرویس خاص برای بررسی'
        )
        
        parser.add_argument(
            '--json',
            action='store_true',
            help='خروجی در فرمت JSON'
        )
        
        parser.add_argument(
            '--fail-on-error',
            action='store_true',
            help='خروج با کد خطا در صورت وجود مشکل'
        )
        
        parser.add_argument(
            '--timeout',
            type=int,
            default=30,
            help='timeout برای بررسی سرویس‌ها (ثانیه)'
        )
    
    def handle(self, *args, **options):
        """اجرای health check"""
        environment_name = options.get('environment')
        service_name = options.get('service')
        output_json = options.get('json')
        fail_on_error = options.get('fail_on_error')
        timeout = options.get('timeout')
        
        # بررسی محیط
        if environment_name:
            try:
                environment = EnvironmentConfig.objects.get(
                    name=environment_name,
                    is_active=True
                )
            except EnvironmentConfig.DoesNotExist:
                raise CommandError(f'محیط {environment_name} یافت نشد')
        
        try:
            # ایجاد سرویس health check
            health_service = HealthService(environment_name)
            
            if service_name:
                # بررسی سرویس خاص
                result = self._check_specific_service(
                    health_service, environment_name, service_name, timeout
                )
            else:
                # بررسی جامع
                result = health_service.comprehensive_health_check()
            
            # نمایش نتایج
            if output_json:
                self.stdout.write(json.dumps(result, indent=2, ensure_ascii=False))
            else:
                self._display_results(result)
            
            # بررسی وضعیت و خروج
            if fail_on_error:
                overall_status = result.get('overall_status', 'unknown')
                if overall_status in ['critical', 'unknown']:
                    sys.exit(1)
                elif overall_status == 'warning':
                    sys.exit(2)  # Warning exit code
                    
        except Exception as e:
            if output_json:
                error_result = {
                    'status': 'error',
                    'message': str(e),
                    'timestamp': str(timezone.now())
                }
                self.stdout.write(json.dumps(error_result, ensure_ascii=False))
            else:
                raise CommandError(f'خطا در health check: {str(e)}')
            
            if fail_on_error:
                sys.exit(1)
    
    def _check_specific_service(self, health_service, environment_name, service_name, timeout):
        """بررسی سرویس خاص"""
        if not environment_name:
            raise CommandError('برای بررسی سرویس خاص، محیط باید مشخص شود')
        
        try:
            # یافتن تنظیمات سرویس
            service_monitoring = ServiceMonitoring.objects.get(
                environment__name=environment_name,
                service_name=service_name,
                is_active=True
            )
            
            # بررسی سرویس
            result = health_service.check_external_service(
                service_monitoring.health_check_url,
                timeout
            )
            
            # ذخیره نتیجه
            health_service._save_health_check_result(service_monitoring, result)
            
            return {
                'service_name': service_name,
                'environment': environment_name,
                'result': result,
                'timestamp': timezone.now().isoformat()
            }
            
        except ServiceMonitoring.DoesNotExist:
            raise CommandError(f'سرویس {service_name} در محیط {environment_name} یافت نشد')
    
    def _display_results(self, result):
        """نمایش نتایج به صورت متنی"""
        if 'service_name' in result:
            # نتیجه سرویس خاص
            service_result = result['result']
            status = service_result.get('status', 'unknown')
            
            self.stdout.write(f"\n🔍 بررسی سرویس: {result['service_name']}")
            self.stdout.write(f"محیط: {result['environment']}")
            
            if status == 'healthy':
                self.stdout.write(self.style.SUCCESS("✅ وضعیت: سالم"))
            elif status == 'warning':
                self.stdout.write(self.style.WARNING("⚠️  وضعیت: هشدار"))
            elif status == 'critical':
                self.stdout.write(self.style.ERROR("❌ وضعیت: بحرانی"))
            else:
                self.stdout.write(f"❓ وضعیت: {status}")
            
            if 'response_time' in service_result:
                self.stdout.write(f"زمان پاسخ: {service_result['response_time']:.2f} ms")
            
            if 'error' in service_result:
                self.stdout.write(self.style.ERROR(f"خطا: {service_result['error']}"))
                
        else:
            # نتیجه جامع
            overall_status = result.get('overall_status', 'unknown')
            
            self.stdout.write("\n🏥 بررسی سلامت کلی سیستم")
            self.stdout.write(f"زمان: {result.get('timestamp', 'نامشخص')}")
            
            if overall_status == 'healthy':
                self.stdout.write(self.style.SUCCESS("✅ وضعیت کلی: سالم"))
            elif overall_status == 'warning':
                self.stdout.write(self.style.WARNING("⚠️  وضعیت کلی: هشدار"))
            elif overall_status == 'critical':
                self.stdout.write(self.style.ERROR("❌ وضعیت کلی: بحرانی"))
            else:
                self.stdout.write(f"❓ وضعیت کلی: {overall_status}")
            
            # نمایش جزئیات سرویس‌ها
            services = result.get('services', {})
            
            if services:
                self.stdout.write("\n📊 جزئیات سرویس‌ها:")
                self.stdout.write("-" * 50)
                
                for service_name, service_data in services.items():
                    status = service_data.get('status', 'unknown')
                    
                    if status == 'healthy':
                        status_icon = "✅"
                        status_style = self.style.SUCCESS
                    elif status == 'warning':
                        status_icon = "⚠️"
                        status_style = self.style.WARNING
                    elif status == 'critical':
                        status_icon = "❌"
                        status_style = self.style.ERROR
                    else:
                        status_icon = "❓"
                        status_style = self.style.NOTICE
                    
                    self.stdout.write(
                        f"{status_icon} {service_name}: {status_style(status)}"
                    )
                    
                    # اطلاعات اضافی
                    if 'response_time' in service_data:
                        self.stdout.write(f"   زمان پاسخ: {service_data['response_time']:.2f} ms")
                    
                    if status == 'critical' and 'error' in service_data:
                        self.stdout.write(f"   خطا: {service_data['error']}")
                    
                    # اطلاعات منابع سیستم
                    if service_name in ['cpu', 'memory', 'disk']:
                        if 'percent_used' in service_data:
                            self.stdout.write(f"   استفاده: {service_data['percent_used']:.1f}%")
            
            # زمان کل بررسی
            if 'total_check_time' in result:
                self.stdout.write(f"\n⏱️  زمان کل بررسی: {result['total_check_time']:.2f} ms")
        
        self.stdout.write("")  # خط خالی در انتها