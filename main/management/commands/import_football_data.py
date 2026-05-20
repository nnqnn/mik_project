import os
import hashlib
import random
import re
import time
from datetime import datetime, timedelta, timezone as datetime_timezone

import requests
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from main.models import Club, Tournament, TournamentClub, Match

API_BASE = "https://api.football-data.org/v4"
DEFAULT_COMPETITIONS = "PL,PD,SA,BL1,FL1"
PAST_MATCH_GRACE_PERIOD = timedelta(hours=2)
FINISHED_API_STATUSES = {"FINISHED", "AWARDED"}
NOT_PLAYED_API_STATUSES = {"CANCELLED", "POSTPONED", "SUSPENDED"}


def parse_iso_datetime(value):
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if timezone.is_naive(dt):
        dt = timezone.make_aware(dt, timezone=datetime_timezone.utc)
    return dt


def parse_market_value(value):
    if value is None:
        return 0
    if isinstance(value, (int, float)):
        return int(value)
    digits = re.sub(r"[^0-9]", "", str(value))
    return int(digits) if digits else 0


def extract_town(address, fallback):
    if not address:
        return fallback
    parts = [part.strip() for part in address.split(",") if part.strip()]
    candidate = parts[-1] if parts else address.strip()
    candidate = re.sub(r"\b\d{4,}\b", "", candidate).strip()
    return candidate or fallback


def needs_random_stats(stats):
    if not isinstance(stats, dict) or not stats:
        return True
    required = (
        "ball_possession",
        "shots",
        "shots_on_goal",
        "saves",
        "red_cards",
    )
    if not all(key in stats for key in required):
        return True
    return all((stats.get(key) in (0, None)) for key in required)


def stable_seed(*parts):
    joined = "|".join("" if part is None else str(part) for part in parts)
    digest = hashlib.sha256(joined.encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big", signed=False)


def generate_match_stats(home_goals, away_goals, seed):
    rng = random.Random(seed)
    home_goals = max(0, int(home_goals or 0))
    away_goals = max(0, int(away_goals or 0))

    home_possession = rng.randint(38, 62)
    away_possession = 100 - home_possession

    home_shots_on_target = max(home_goals, rng.randint(home_goals, home_goals + 6))
    away_shots_on_target = max(away_goals, rng.randint(away_goals, away_goals + 6))

    home_shots = max(home_shots_on_target, home_shots_on_target + rng.randint(2, 10))
    away_shots = max(away_shots_on_target, away_shots_on_target + rng.randint(2, 10))

    home_saves = max(0, away_shots_on_target - away_goals)
    away_saves = max(0, home_shots_on_target - home_goals)

    def red_cards():
        return rng.choices([0, 1, 2], weights=[85, 13, 2])[0]

    return {
        "home": {
            "ball_possession": home_possession,
            "shots": home_shots,
            "shots_on_goal": home_shots_on_target,
            "saves": home_saves,
            "red_cards": red_cards(),
        },
        "away": {
            "ball_possession": away_possession,
            "shots": away_shots,
            "shots_on_goal": away_shots_on_target,
            "saves": away_saves,
            "red_cards": red_cards(),
        },
    }


def generate_match_score(seed):
    rng = random.Random(seed)
    goal_values = [0, 1, 2, 3, 4, 5]
    home_weights = [14, 26, 28, 19, 9, 4]
    away_weights = [20, 30, 26, 15, 6, 3]
    return (
        rng.choices(goal_values, weights=home_weights)[0],
        rng.choices(goal_values, weights=away_weights)[0],
    )


def match_is_finished(api_status, dt, now=None):
    api_status = (api_status or "").upper()
    if api_status in FINISHED_API_STATUSES:
        return True
    if api_status in NOT_PLAYED_API_STATUSES or dt is None:
        return False
    now = now or timezone.now()
    return dt <= now - PAST_MATCH_GRACE_PERIOD


def generate_club_price(club, tournament_name=None):
    top_leagues = {
        "Англия",
        "Испания",
        "Италия",
        "Германия",
        "Франция",
    }
    seed = stable_seed("club-price", club.name, club.country, tournament_name)
    rng = random.Random(seed)
    if club.country in top_leagues:
        return rng.randint(120_000_000, 1_500_000_000)
    return rng.randint(15_000_000, 400_000_000)


def update_club_aggregates(club):
    matches = (
        Match.objects.filter(Q(home_club=club) | Q(away_club=club), status="finished")
        .order_by("-datetime")[:5]
    )
    if not matches:
        club.goals = 0.0
        club.goals_missed = 0.0
        club.possession = 0
        return

    goals_for = 0
    goals_against = 0
    possession_total = 0
    count = 0
    for match in matches:
        if match.home_club_id == club.id:
            goals_for += match.home_goals
            goals_against += match.away_goals
            possession_total += match.home_possession
        else:
            goals_for += match.away_goals
            goals_against += match.home_goals
            possession_total += match.away_possession
        count += 1

    club.goals = round(goals_for / count, 1)
    club.goals_missed = round(goals_against / count, 1)
    club.possession = round(possession_total / count)


def update_club_form(club):
    finished_matches = (
        Match.objects.filter(Q(home_club=club) | Q(away_club=club), status="finished")
        .order_by("-datetime")[:5]
    )
    results = [0, 0, 0, 0, 0]
    for index, match in enumerate(finished_matches):
        if match.home_club_id == club.id:
            club_goals = match.home_goals
            opponent_goals = match.away_goals
        else:
            club_goals = match.away_goals
            opponent_goals = match.home_goals

        if club_goals > opponent_goals:
            results[index] = 3
        elif club_goals == opponent_goals:
            results[index] = 1

    club.match_1, club.match_2, club.match_3, club.match_4, club.match_5 = results
    club.next_match = int(
        Match.objects.filter(
            Q(home_club=club) | Q(away_club=club),
            status="scheduled",
            datetime__gt=timezone.now(),
        ).exists()
    )


class Command(BaseCommand):
    help = "Импорт данных из football-data.org в модели проекта"

    def add_arguments(self, parser):
        parser.add_argument(
            "--competitions",
            default=DEFAULT_COMPETITIONS,
            help="Коды лиг через запятую (по умолчанию PL,PD,SA,BL1,FL1)",
        )
        parser.add_argument(
            "--season",
            type=int,
            default=None,
            help="Сезон в формате YYYY (например, 2023)",
        )
        parser.add_argument(
            "--clear",
            action="store_true",
            help="Очистить существующие данные перед импортом",
        )
        parser.add_argument(
            "--skip-teams",
            action="store_true",
            help="Не импортировать команды",
        )
        parser.add_argument(
            "--skip-standings",
            action="store_true",
            help="Не импортировать турнирные таблицы",
        )
        parser.add_argument(
            "--skip-matches",
            action="store_true",
            help="Не импортировать матчи",
        )
        parser.add_argument(
            "--limit-matches",
            type=int,
            default=0,
            help="Ограничить количество импортируемых матчей (0 = без ограничения)",
        )

    def handle(self, *args, **options):
        token = os.getenv("FOOTBALL_DATA_TOKEN") or os.getenv("FOOTBALL_DATA_API_KEY")
        if not token:
            raise CommandError(
                "Не найден API-токен. Установите переменную окружения "
                "FOOTBALL_DATA_TOKEN или FOOTBALL_DATA_API_KEY."
            )

        competitions = [
            code.strip().upper()
            for code in options["competitions"].split(",")
            if code.strip()
        ]
        if not competitions:
            raise CommandError("Список лиг пустой. Укажите --competitions=PL,PD,...")

        params = {}
        if options["season"]:
            params["season"] = str(options["season"])

        session = requests.Session()
        session.headers.update({"X-Auth-Token": token})

        def api_get(path, extra_params=None, max_retries=3):
            request_params = dict(params)
            if extra_params:
                request_params.update(extra_params)
            url = f"{API_BASE}{path}"
            attempts = 0
            while True:
                response = session.get(url, params=request_params, timeout=30)
                if response.status_code == 200:
                    return response.json()
                if response.status_code == 429 and attempts < max_retries:
                    attempts += 1
                    wait_seconds = 60
                    try:
                        payload = response.json()
                        message = payload.get("message", "")
                        match = re.search(r"Wait\\s+(\\d+)\\s+seconds", message)
                        if match:
                            wait_seconds = int(match.group(1))
                    except ValueError:
                        pass
                    self.stdout.write(
                        self.style.WARNING(
                            f"Лимит запросов. Ждём {wait_seconds} секунд и пробуем снова..."
                        )
                    )
                    time.sleep(wait_seconds)
                    continue
                raise CommandError(
                    f"API error {response.status_code} for {url}: {response.text}"
                )

        if options["clear"]:
            self.stdout.write(self.style.WARNING("Очищаем существующие данные..."))
            Match.objects.all().delete()
            TournamentClub.objects.all().delete()
            Club.objects.all().delete()
            Tournament.objects.all().delete()

        for code in competitions:
            self.stdout.write(self.style.MIGRATE_HEADING(f"Импорт лиги {code}"))
            with transaction.atomic():

                competition = api_get(f"/competitions/{code}")
                area = competition.get("area", {})
                tournament_defaults = {
                    "country": area.get("name", ""),
                }
                emblem_url = (
                    competition.get("emblem")
                    or competition.get("emblemUrl")
                    or competition.get("emblem_url")
                )
                if emblem_url:
                    tournament_defaults["logo_url"] = emblem_url

                tournament, _ = Tournament.objects.update_or_create(
                    name=competition.get("name", code),
                    defaults=tournament_defaults,
                )

                team_map = {}
                if not options["skip_teams"]:
                    teams_payload = api_get(f"/competitions/{code}/teams")
                    for team in teams_payload.get("teams", []):
                        team_area = team.get("area", {})
                        country = team_area.get("name") or area.get("name") or ""
                        town = extract_town(team.get("address"), country)
                        club_defaults = {
                            "town": town,
                            "price": parse_market_value(team.get("marketValue")),
                            "founded": team.get("founded") or 0,
                            "stadium": team.get("venue") or "Unknown",
                            "match_1": 0,
                            "match_2": 0,
                            "match_3": 0,
                            "match_4": 0,
                            "match_5": 0,
                            "next_match": 0,
                            "goals": 0.0,
                            "goals_missed": 0.0,
                            "possession": 0,
                        }
                        crest_url = (
                            team.get("crest")
                            or team.get("crestUrl")
                            or team.get("crest_url")
                        )
                        if crest_url:
                            club_defaults["emblem_url"] = crest_url
                        club, _ = Club.objects.update_or_create(
                            name=team.get("name", "Unknown"),
                            country=country,
                            defaults=club_defaults,
                        )
                        if team.get("id") is not None:
                            team_map[team["id"]] = club

                if not options["skip_standings"]:
                    standings_payload = api_get(f"/competitions/{code}/standings")
                    standings = standings_payload.get("standings", [])
                    total_table = None
                    for standing in standings:
                        if standing.get("type") == "TOTAL":
                            total_table = standing.get("table", [])
                            break
                    if total_table is None and standings:
                        total_table = standings[0].get("table", [])

                    for row in total_table or []:
                        team = row.get("team", {})
                        club = team_map.get(team.get("id"))
                        if club is None:
                            crest_url = (
                                team.get("crest")
                                or team.get("crestUrl")
                                or team.get("crest_url")
                            )
                            club_defaults = {
                                "town": area.get("name", ""),
                                "price": 0,
                                "founded": 0,
                                "stadium": "Unknown",
                                "match_1": 0,
                                "match_2": 0,
                                "match_3": 0,
                                "match_4": 0,
                                "match_5": 0,
                                "next_match": 0,
                                "goals": 0.0,
                                "goals_missed": 0.0,
                                "possession": 0,
                            }
                            if crest_url:
                                club_defaults["emblem_url"] = crest_url
                            club, _ = Club.objects.update_or_create(
                                name=team.get("name", "Unknown"),
                                country=area.get("name", ""),
                                defaults=club_defaults,
                            )
                            if team.get("id") is not None:
                                team_map[team.get("id")] = club

                        TournamentClub.objects.update_or_create(
                            tournament=tournament,
                            club=club,
                            defaults={
                                "matches_played": row.get("playedGames") or 0,
                                "wins": row.get("won") or 0,
                                "draws": row.get("draw") or 0,
                                "losses": row.get("lost") or 0,
                                "goals_for": row.get("goalsFor") or 0,
                                "goals_against": row.get("goalsAgainst") or 0,
                            },
                        )

                if not options["skip_matches"]:
                    matches_payload = api_get(f"/competitions/{code}/matches")
                    matches = matches_payload.get("matches", [])
                    limit = options["limit_matches"] or 0
                    if limit > 0:
                        matches = matches[:limit]

                    for match in matches:
                        home = match.get("homeTeam", {})
                        away = match.get("awayTeam", {})
                        home_club = team_map.get(home.get("id"))
                        away_club = team_map.get(away.get("id"))

                        if home_club is None:
                            crest_url = (
                                home.get("crest")
                                or home.get("crestUrl")
                                or home.get("crest_url")
                            )
                            club_defaults = {
                                "town": area.get("name", ""),
                                "price": 0,
                                "founded": 0,
                                "stadium": "Unknown",
                                "match_1": 0,
                                "match_2": 0,
                                "match_3": 0,
                                "match_4": 0,
                                "match_5": 0,
                                "next_match": 0,
                                "goals": 0.0,
                                "goals_missed": 0.0,
                                "possession": 0,
                            }
                            if crest_url:
                                club_defaults["emblem_url"] = crest_url
                            home_club, _ = Club.objects.update_or_create(
                                name=home.get("name", "Unknown"),
                                country=area.get("name", ""),
                                defaults=club_defaults,
                            )
                        if away_club is None:
                            crest_url = (
                                away.get("crest")
                                or away.get("crestUrl")
                                or away.get("crest_url")
                            )
                            club_defaults = {
                                "town": area.get("name", ""),
                                "price": 0,
                                "founded": 0,
                                "stadium": "Unknown",
                                "match_1": 0,
                                "match_2": 0,
                                "match_3": 0,
                                "match_4": 0,
                                "match_5": 0,
                                "next_match": 0,
                                "goals": 0.0,
                                "goals_missed": 0.0,
                                "possession": 0,
                            }
                            if crest_url:
                                club_defaults["emblem_url"] = crest_url
                            away_club, _ = Club.objects.update_or_create(
                                name=away.get("name", "Unknown"),
                                country=area.get("name", ""),
                                defaults=club_defaults,
                            )

                        dt = parse_iso_datetime(match.get("utcDate"))
                        if dt is None:
                            continue

                        score = match.get("score", {})
                        full_time = score.get("fullTime", {}) or {}
                        api_status = match.get("status")
                        is_finished = match_is_finished(api_status, dt)
                        score_seed = stable_seed(
                            match.get("id"),
                            home.get("name"),
                            away.get("name"),
                            dt.isoformat(),
                            "score",
                        )
                        home_goals = full_time.get("home")
                        away_goals = full_time.get("away")
                        if is_finished and (home_goals is None or away_goals is None):
                            home_goals, away_goals = generate_match_score(score_seed)
                        else:
                            home_goals = home_goals or 0
                            away_goals = away_goals or 0

                        home_stats = (home.get("statistics") or {})
                        away_stats = (away.get("statistics") or {})
                        if needs_random_stats(home_stats) or needs_random_stats(away_stats):
                            seed = stable_seed(
                                match.get("id"),
                                home.get("name"),
                                away.get("name"),
                                dt.isoformat() if dt else "",
                                home_goals,
                                away_goals,
                            )
                            synthetic = generate_match_stats(
                                home_goals,
                                away_goals,
                                seed=seed,
                            )
                            home_stats = synthetic["home"]
                            away_stats = synthetic["away"]

                        Match.objects.update_or_create(
                            home_club=home_club,
                            away_club=away_club,
                            tournament=tournament,
                            datetime=dt,
                            defaults={
                                "town": home_club.town,
                                "stadium": match.get("venue") or home_club.stadium,
                                "home_goals": home_goals,
                                "away_goals": away_goals,
                                "home_possession": home_stats.get("ball_possession") or 0,
                                "away_possession": away_stats.get("ball_possession") or 0,
                                "home_shots": home_stats.get("shots") or 0,
                                "away_shots": away_stats.get("shots") or 0,
                                "home_shots_on_target": home_stats.get("shots_on_goal") or 0,
                                "away_shots_on_target": away_stats.get("shots_on_goal") or 0,
                                "home_red_cards": home_stats.get("red_cards") or 0,
                                "away_red_cards": away_stats.get("red_cards") or 0,
                                "home_saves": home_stats.get("saves") or 0,
                                "away_saves": away_stats.get("saves") or 0,
                                "status": "finished" if is_finished else "scheduled",
                            },
                        )

            self.stdout.write(self.style.SUCCESS(f"Импорт {code} завершен"))

        self.stdout.write(self.style.MIGRATE_HEADING("Обновляем статистику клубов..."))
        for club in Club.objects.all():
            update_club_aggregates(club)
            update_club_form(club)
            if club.price <= 0:
                tournament_name = club.tournaments.first().name if club.tournaments.exists() else None
                club.price = generate_club_price(club, tournament_name=tournament_name)
            club.save(
                update_fields=[
                    "goals",
                    "goals_missed",
                    "possession",
                    "price",
                    "match_1",
                    "match_2",
                    "match_3",
                    "match_4",
                    "match_5",
                    "next_match",
                ]
            )
