
import json

from django.core.management.base import BaseCommand, CommandError

from terminal.models import Terminal
from vehicle_fleet.models import GateCamera
from vehicle_fleet_integration.dahua_stream_worker import run_dahua_stream_worker
from vehicle_fleet_integration.event_parser import extract_plate_event
from vehicle_fleet_integration.event_processor import process_plate_event
from vehicle_fleet_integration.stream_worker import run_stream_worker


class Command(BaseCommand):
    help = (
        'Запускает интеграцию с Macroscop или Dahua-камерой для терминала. '
        'Режим --source=dahua подключается напрямую к камере (не через Macroscop). '
        'Режим --fixture — offline-прогон событий из локального JSON-файла.'
    )

    def add_arguments(self, parser):
        parser.add_argument('--terminal-id', type=int, required=True)
        parser.add_argument(
            '--source', default='macroscop', choices=['macroscop', 'dahua'],
            help='Источник событий: macroscop (по умолчанию) или dahua (прямое подключение к камере).',
        )
        # Macroscop-специфичные аргументы
        parser.add_argument('--channel-id', default=None, help='UUID канала Macroscop (опционально)')
        parser.add_argument('--event-filter', default=None, help='UUID типа события "Обнаружен автономер"')
        parser.add_argument(
            '--mode', default=None, choices=['demo'],
            help='Передаётся серверу как mode=demo (виртуальные события Macroscop).',
        )
        # Dahua-специфичные аргументы
        parser.add_argument(
            '--gate-camera-id', type=int, default=None,
            help='pk GateCamera для этой Dahua-камеры (подставляет channel_id и роль).',
        )
        # Общие
        parser.add_argument(
            '--fixture', default=None,
            help='Путь к локальному JSON-файлу (объект или список событий) — offline-прогон без сети.',
        )

    def handle(self, *args, **options):
        try:
            terminal = Terminal.objects.get(pk=options['terminal_id'])
        except Terminal.DoesNotExist as exc:
            raise CommandError(f'Терминал {options["terminal_id"]} не найден') from exc

        if options['fixture']:
            self._replay_fixture(terminal, options['fixture'])
            return

        source = options['source']

        if source == 'dahua':
            gate_camera = None
            if options['gate_camera_id']:
                try:
                    gate_camera = GateCamera.objects.get(pk=options['gate_camera_id'], terminal=terminal)
                except GateCamera.DoesNotExist as exc:
                    raise CommandError(
                        f'GateCamera {options["gate_camera_id"]} не найдена для терминала {terminal.pk}'
                    ) from exc

            self.stdout.write(self.style.SUCCESS(
                f'Запуск Dahua-интеграции для терминала "{terminal.name}"'
                + (f' (камера: {gate_camera.name})' if gate_camera else ''),
            ))
            run_dahua_stream_worker(terminal, gate_camera=gate_camera)

        else:
            self.stdout.write(self.style.SUCCESS(
                f'Запуск Macroscop-интеграции для терминала "{terminal.name}" '
                f'(mode={options["mode"] or "live"})',
            ))
            run_stream_worker(
                terminal,
                channel_id=options['channel_id'],
                event_filter=options['event_filter'],
                mode=options['mode'],
            )

    def _replay_fixture(self, terminal, fixture_path):
        with open(fixture_path, encoding='utf-8') as fh:
            content = json.load(fh)
        events = content if isinstance(content, list) else [content]

        created = 0
        for data in events:
            parsed_event = extract_plate_event(data)
            if parsed_event is None:
                self.stdout.write(self.style.WARNING(
                    f'Событие пропущено на этапе парсинга: {data.get("EventId")}',
                ))
                continue
            gate_pass = process_plate_event(parsed_event, terminal=terminal)
            if gate_pass is not None:
                created += 1
                self.stdout.write(self.style.SUCCESS(
                    f'Создан VehicleGatePass #{gate_pass.pk} '
                    f'({gate_pass.registration_number}, {gate_pass.direction})',
                ))
            else:
                self.stdout.write(self.style.WARNING(
                    f'Событие {data.get("EventId")} отброшено обработчиком',
                ))

        self.stdout.write(f'Готово: создано {created} из {len(events)} событий.')