"""
Management command برای مدیریت Docker
"""
from django.core.management.base import BaseCommand, CommandError
from devops.services.docker_service import DockerService, DockerComposeService
import json
import sys


class Command(BaseCommand):
    """
    دستور مدیریت Docker از طریق CLI
    
    استفاده:
    python manage.py docker_manage --action ps
    python manage.py docker_manage --action restart --container web
    python manage.py docker_manage --action compose-status
    python manage.py docker_manage --action compose-restart --services web worker
    """
    
    help = 'مدیریت Docker containers و compose services'
    
    def add_arguments(self, parser):
        """تعریف آرگومان‌های command"""
        parser.add_argument(
            '-a', '--action',
            type=str,
            required=True,
            choices=[
                'ps', 'restart', 'stop', 'start', 'logs',
                'compose-status', 'compose-start', 'compose-stop', 
                'compose-restart', 'compose-build', 'compose-pull'
            ],
            help='عملیات مورد نظر'
        )
        
        parser.add_argument(
            '-c', '--container',
            type=str,
            help='نام container برای عملیات‌های تک container'
        )
        
        parser.add_argument(
            '-s', '--services',
            nargs='*',
            help='لیست نام سرویس‌ها برای عملیات‌های compose'
        )
        
        parser.add_argument(
            '--compose-file',
            type=str,
            default='docker-compose.yml',
            help='مسیر فایل docker-compose'
        )
        
        parser.add_argument(
            '--lines',
            type=int,
            default=100,
            help='تعداد خطوط لاگ برای نمایش'
        )
        
        parser.add_argument(
            '--no-cache',
            action='store_true',
            help='عدم استفاده از cache برای build'
        )
        
        parser.add_argument(
            '--json',
            action='store_true',
            help='خروجی در فرمت JSON'
        )
    
    def handle(self, *args, **options):
        """اجرای command"""
        action = options['action']
        container_name = options.get('container')
        services = options.get('services', [])
        compose_file = options['compose_file']
        lines = options['lines']
        no_cache = options['no_cache']
        output_json = options['json']
        
        try:
            if action.startswith('compose-'):
                # عملیات Docker Compose
                result = self._handle_compose_action(
                    action, services, compose_file, no_cache, lines
                )
            else:
                # عملیات Docker Container
                result = self._handle_container_action(
                    action, container_name, lines
                )
            
            # نمایش نتایج
            if output_json:
                self.stdout.write(json.dumps(result, indent=2, ensure_ascii=False))
            else:
                self._display_result(action, result)
                
        except Exception as e:
            if output_json:
                error_result = {
                    'success': False,
                    'error': str(e)
                }
                self.stdout.write(json.dumps(error_result, ensure_ascii=False))
            else:
                raise CommandError(f'خطا در {action}: {str(e)}')
    
    def _handle_container_action(self, action, container_name, lines):
        """مدیریت عملیات container"""
        docker_service = DockerService()
        
        if action == 'ps':
            # لیست containers
            containers = docker_service.get_all_containers()
            return {
                'action': 'ps',
                'success': True,
                'containers': containers,
                'total_count': len(containers)
            }
            
        elif action in ['restart', 'stop', 'start']:
            if not container_name:
                raise CommandError(f'برای عملیات {action} باید نام container مشخص شود')
            
            if action == 'restart':
                success, message = docker_service.restart_container(container_name)
            elif action == 'stop':
                success, message = docker_service.stop_container(container_name)
            elif action == 'start':
                success, message = docker_service.start_container(container_name)
            
            return {
                'action': action,
                'container': container_name,
                'success': success,
                'message': message
            }
            
        elif action == 'logs':
            if not container_name:
                raise CommandError('برای دریافت لاگ باید نام container مشخص شود')
            
            logs = docker_service.get_container_logs(container_name, lines)
            return {
                'action': 'logs',
                'container': container_name,
                'success': True,
                'logs': logs
            }
        
        else:
            raise CommandError(f'عملیات {action} شناخته شده نیست')
    
    def _handle_compose_action(self, action, services, compose_file, no_cache, lines):
        """مدیریت عملیات Docker Compose"""
        compose_service = DockerComposeService(compose_file)
        
        if action == 'compose-status':
            # وضعیت سرویس‌ها
            status = compose_service.get_services_status()
            return {
                'action': 'compose-status',
                'compose_file': compose_file,
                **status
            }
            
        elif action == 'compose-start':
            success, message = compose_service.start_services(services if services else None)
            return {
                'action': 'compose-start',
                'services': services,
                'success': success,
                'message': message
            }
            
        elif action == 'compose-stop':
            success, message = compose_service.stop_services(services if services else None)
            return {
                'action': 'compose-stop',
                'services': services,
                'success': success,
                'message': message
            }
            
        elif action == 'compose-restart':
            success, message = compose_service.restart_services(services if services else None)
            return {
                'action': 'compose-restart',
                'services': services,
                'success': success,
                'message': message
            }
            
        elif action == 'compose-build':
            success, message = compose_service.build_services(
                services if services else None,
                no_cache
            )
            return {
                'action': 'compose-build',
                'services': services,
                'no_cache': no_cache,
                'success': success,
                'message': message
            }
            
        elif action == 'compose-pull':
            success, message = compose_service.pull_images(services if services else None)
            return {
                'action': 'compose-pull',
                'services': services,
                'success': success,
                'message': message
            }
        
        else:
            raise CommandError(f'عملیات {action} شناخته شده نیست')
    
    def _display_result(self, action, result):
        """نمایش نتایج به صورت متنی"""
        if action == 'ps':
            # نمایش لیست containers
            containers = result.get('containers', [])
            
            self.stdout.write(f"\n🐳 لیست Docker Containers ({len(containers)} container)")
            self.stdout.write("-" * 80)
            
            if containers:
                for container in containers:
                    status = container.get('status', 'unknown')
                    
                    if status == 'running':
                        status_icon = "✅"
                        status_style = self.style.SUCCESS
                    elif status in ['exited', 'stopped']:
                        status_icon = "⏹️"
                        status_style = self.style.WARNING
                    else:
                        status_icon = "❓"
                        status_style = self.style.NOTICE
                    
                    self.stdout.write(
                        f"{status_icon} {container['name']:<20} {status_style(status):<15} {container.get('image', 'unknown')}"
                    )
            else:
                self.stdout.write("هیچ container یافت نشد")
                
        elif action == 'logs':
            # نمایش لاگ‌ها
            container = result.get('container', 'unknown')
            logs = result.get('logs', '')
            
            self.stdout.write(f"\n📋 لاگ‌های container: {container}")
            self.stdout.write("-" * 50)
            self.stdout.write(logs)
            
        elif action == 'compose-status':
            # وضعیت Docker Compose
            services = result.get('services', [])
            total_services = result.get('total_services', 0)
            running_services = result.get('running_services', 0)
            
            self.stdout.write(f"\n🐙 وضعیت Docker Compose Services")
            self.stdout.write(f"فایل: {result.get('compose_file', 'نامشخص')}")
            self.stdout.write(f"کل سرویس‌ها: {total_services}")
            self.stdout.write(f"سرویس‌های در حال اجرا: {running_services}")
            self.stdout.write("-" * 60)
            
            if services:
                for service in services:
                    name = service.get('Name', 'unknown')
                    state = service.get('State', 'unknown')
                    
                    if state == 'running':
                        state_icon = "✅"
                        state_style = self.style.SUCCESS
                    elif state in ['exited', 'stopped']:
                        state_icon = "⏹️"
                        state_style = self.style.WARNING
                    else:
                        state_icon = "❓"
                        state_style = self.style.NOTICE
                    
                    self.stdout.write(
                        f"{state_icon} {name:<20} {state_style(state):<15}"
                    )
            else:
                self.stdout.write("هیچ سرویسی یافت نشد")
                
        else:
            # سایر عملیات
            success = result.get('success', False)
            message = result.get('message', '')
            
            if success:
                self.stdout.write(self.style.SUCCESS(f"\n✅ {action} با موفقیت انجام شد"))
            else:
                self.stdout.write(self.style.ERROR(f"\n❌ {action} ناموفق بود"))
            
            if message:
                self.stdout.write(f"پیام: {message}")
            
            # اطلاعات اضافی
            for key, value in result.items():
                if key not in ['success', 'message', 'action']:
                    self.stdout.write(f"{key}: {value}")
        
        self.stdout.write("")  # خط خالی در انتها