import os

from django.core.management import call_command
from django.core.management.base import CommandError
from django.core.management.commands.runserver import Command as RunserverCommand


class Command(RunserverCommand):
    help = (
        "Запускает сервер разработки и перед стартом обновляет данные "
        "из football-data.org (если задан токен)."
    )

    def handle(self, *args, **options):
        # Автообновление данных только на фактическом старте сервера,
        # чтобы не выполнять импорт дважды из-за autoreload.
        should_import = os.environ.get("RUN_MAIN") == "true" or not options.get(
            "use_reloader", True
        )
        if should_import:
            if os.environ.get("SKIP_FOOTBALL_IMPORT") != "1":
                competitions = os.environ.get("FOOTBALL_DATA_COMPETITIONS")
                season = os.environ.get("FOOTBALL_DATA_SEASON")
                clear = os.environ.get("FOOTBALL_DATA_CLEAR") == "1"
                limit_matches = os.environ.get("FOOTBALL_DATA_LIMIT_MATCHES")

                kwargs = {}
                if competitions:
                    kwargs["competitions"] = competitions
                if season:
                    try:
                        kwargs["season"] = int(season)
                    except ValueError:
                        self.stderr.write(
                            self.style.WARNING(
                                f"Игнорируем некорректный FOOTBALL_DATA_SEASON={season}"
                            )
                        )
                if clear:
                    kwargs["clear"] = True
                if limit_matches:
                    try:
                        kwargs["limit_matches"] = int(limit_matches)
                    except ValueError:
                        self.stderr.write(
                            self.style.WARNING(
                                f"Игнорируем некорректный FOOTBALL_DATA_LIMIT_MATCHES={limit_matches}"
                            )
                        )

                self.stdout.write(self.style.MIGRATE_HEADING("Авто-импорт данных..."))
                try:
                    call_command("import_football_data", **kwargs)
                except CommandError as exc:
                    self.stderr.write(
                        self.style.WARNING(
                            f"Импорт пропущен: {exc}"
                        )
                    )

        super().handle(*args, **options)
