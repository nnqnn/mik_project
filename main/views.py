from django.http import JsonResponse
from django.shortcuts import render, get_object_or_404, redirect
from django.db.models import Q
from .models import Club, Match, Tournament
from django.shortcuts import render, get_object_or_404
from django.db.models import Q, F, Count, Sum, Case, When, IntegerField
from django.db.models.functions import Coalesce
from .models import Club, Match, Tournament, TournamentClub
from django.db import transaction
from datetime import datetime, timedelta
import random
import os

from django.db import connection
from .metrics import metrics_view


def frontend_service_urls():
    return {
        "auth_api_url": os.getenv("FRONTEND_AUTH_API_URL", "http://localhost:8003").rstrip("/"),
        "ticketing_api_url": os.getenv("FRONTEND_TICKETING_API_URL", "http://localhost:8001").rstrip("/"),
        "payment_api_url": os.getenv("FRONTEND_PAYMENT_API_URL", "http://localhost:8002").rstrip("/"),
    }

def load_tournament_data():
    """Загрузка данных для турниров по 6 клубов каждый с полным кругом матчей"""
    print("=" * 60)
    print("НАЧИНАЕМ ЗАГРУЗКУ ДАННЫХ")
    print("=" * 60)
    
    with transaction.atomic():
        # Шаг 1: Создаем или получаем турниры
        print("\n1. Создаем турниры...")
        
        # Удаляем старые турниры и создаем заново
        Tournament.objects.all().delete()
        
        # Создаем турниры
        tournament_apl = Tournament.objects.create(
            name='Английская Премьер-лига',
            country='Англия'
        )
        
        tournament_ll = Tournament.objects.create(
            name='Ла Лига',
            country='Испания'
        )
        
        tournament_sa = Tournament.objects.create(
            name='Серия А',
            country='Италия'
        )
        
        tournament_bl = Tournament.objects.create(
            name='Бундеслига',
            country='Германия'
        )
        
        tournament_l1 = Tournament.objects.create(
            name='Лига 1',
            country='Франция'
        )
        
        tournaments = [tournament_apl, tournament_ll, tournament_sa, tournament_bl, tournament_l1]
        print(f"   Создано {len(tournaments)} турниров")

        # Шаг 2: Очищаем старые данные
        print("\n2. Очищаем старые данные...")
        match_count = Match.objects.count()
        tournamentclub_count = TournamentClub.objects.count()
        club_count = Club.objects.count()
        
        Match.objects.all().delete()
        TournamentClub.objects.all().delete()
        Club.objects.all().delete()
        
        print(f"   Удалено: {match_count} матчей, {tournamentclub_count} турнирных записей, {club_count} клубов")

        # Шаг 3: Создаем клубы
        print("\n3. Создаем клубы...")
        
        # АНГЛИЙСКАЯ ПРЕМЬЕР-ЛИГА
        print("   Создаем клубы АПЛ...")
        man_city = Club.objects.create(
            name='Манчестер Сити', country='Англия', town='Манчестер',
            price=1250000000, founded=1880, stadium='Этихад',
            match_1=0, match_2=0, match_3=0, match_4=0, match_5=0, next_match=0,
            goals=2.8, goals_missed=0.9, possession=65
        )
        arsenal = Club.objects.create(
            name='Арсенал', country='Англия', town='Лондон',
            price=1100000000, founded=1886, stadium='Эмирейтс',
            match_1=0, match_2=0, match_3=0, match_4=0, match_5=0, next_match=0,
            goals=2.5, goals_missed=1.0, possession=62
        )
        liverpool = Club.objects.create(
            name='Ливерпуль', country='Англия', town='Ливерпуль',
            price=900000000, founded=1892, stadium='Энфилд',
            match_1=0, match_2=0, match_3=0, match_4=0, match_5=0, next_match=0,
            goals=2.6, goals_missed=1.1, possession=63
        )
        chelsea = Club.objects.create(
            name='Челси', country='Англия', town='Лондон',
            price=850000000, founded=1905, stadium='Стэмфорд Бридж',
            match_1=0, match_2=0, match_3=0, match_4=0, match_5=0, next_match=0,
            goals=1.8, goals_missed=1.5, possession=58
        )
        man_united = Club.objects.create(
            name='Манчестер Юнайтед', country='Англия', town='Манчестер',
            price=950000000, founded=1878, stadium='Олд Траффорд',
            match_1=0, match_2=0, match_3=0, match_4=0, match_5=0, next_match=0,
            goals=1.9, goals_missed=1.4, possession=55
        )
        tottenham = Club.objects.create(
            name='Тоттенхэм', country='Англия', town='Лондон',
            price=800000000, founded=1882, stadium='Тоттенхэм Хотспур',
            match_1=0, match_2=0, match_3=0, match_4=0, match_5=0, next_match=0,
            goals=2.1, goals_missed=1.6, possession=57
        )

        # ЛА ЛИГА
        print("   Создаем клубы Ла Лиги...")
        real_madrid = Club.objects.create(
            name='Реал Мадрид', country='Испания', town='Мадрид',
            price=1200000000, founded=1902, stadium='Сантьяго Бернабеу',
            match_1=0, match_2=0, match_3=0, match_4=0, match_5=0, next_match=0,
            goals=2.7, goals_missed=0.8, possession=60
        )
        barcelona = Club.objects.create(
            name='Барселона', country='Испания', town='Барселона',
            price=1100000000, founded=1899, stadium='Камп Ноу',
            match_1=0, match_2=0, match_3=0, match_4=0, match_5=0, next_match=0,
            goals=2.4, goals_missed=0.9, possession=68
        )
        atletico = Club.objects.create(
            name='Атлетико Мадрид', country='Испания', town='Мадрид',
            price=850000000, founded=1903, stadium='Ванда Метрополитано',
            match_1=0, match_2=0, match_3=0, match_4=0, match_5=0, next_match=0,
            goals=1.9, goals_missed=0.7, possession=52
        )
        sevilla = Club.objects.create(
            name='Севилья', country='Испания', town='Севилья',
            price=400000000, founded=1890, stadium='Рамон Санчес Писхуан',
            match_1=0, match_2=0, match_3=0, match_4=0, match_5=0, next_match=0,
            goals=1.5, goals_missed=1.3, possession=54
        )
        valencia = Club.objects.create(
            name='Валенсия', country='Испания', town='Валенсия',
            price=350000000, founded=1919, stadium='Месталья',
            match_1=0, match_2=0, match_3=0, match_4=0, match_5=0, next_match=0,
            goals=1.6, goals_missed=1.4, possession=53
        )
        villarreal = Club.objects.create(
            name='Вильярреал', country='Испания', town='Вильярреаль',
            price=380000000, founded=1923, stadium='Ла Керамика',
            match_1=0, match_2=0, match_3=0, match_4=0, match_5=0, next_match=0,
            goals=1.8, goals_missed=1.2, possession=56
        )

        # СЕРИЯ А
        print("   Создаем клубы Серии А...")
        inter = Club.objects.create(
            name='Интер', country='Италия', town='Милан',
            price=900000000, founded=1908, stadium='Джузеппе Меацца',
            match_1=0, match_2=0, match_3=0, match_4=0, match_5=0, next_match=0,
            goals=2.5, goals_missed=0.6, possession=58
        )
        juventus = Club.objects.create(
            name='Ювентус', country='Италия', town='Турин',
            price=850000000, founded=1897, stadium='Альянц',
            match_1=0, match_2=0, match_3=0, match_4=0, match_5=0, next_match=0,
            goals=2.0, goals_missed=0.8, possession=55
        )
        ac_milan = Club.objects.create(
            name='Милан', country='Италия', town='Милан',
            price=800000000, founded=1899, stadium='Сан-Сиро',
            match_1=0, match_2=0, match_3=0, match_4=0, match_5=0, next_match=0,
            goals=2.1, goals_missed=1.1, possession=56
        )
        napoli = Club.objects.create(
            name='Наполи', country='Италия', town='Неаполь',
            price=750000000, founded=1926, stadium='Диего Марадона',
            match_1=0, match_2=0, match_3=0, match_4=0, match_5=0, next_match=0,
            goals=2.2, goals_missed=1.3, possession=57
        )
        roma = Club.objects.create(
            name='Рома', country='Италия', town='Рим',
            price=500000000, founded=1927, stadium='Олимпико',
            match_1=0, match_2=0, match_3=0, match_4=0, match_5=0, next_match=0,
            goals=1.8, goals_missed=1.4, possession=54
        )
        lazio = Club.objects.create(
            name='Лацио', country='Италия', town='Рим',
            price=450000000, founded=1900, stadium='Олимпико',
            match_1=0, match_2=0, match_3=0, match_4=0, match_5=0, next_match=0,
            goals=1.7, goals_missed=1.2, possession=53
        )

        # БУНДЕСЛИГА
        print("   Создаем клубы Бундеслиги...")
        bayern = Club.objects.create(
            name='Бавария', country='Германия', town='Мюнхен',
            price=1000000000, founded=1900, stadium='Альянц Арена',
            match_1=0, match_2=0, match_3=0, match_4=0, match_5=0, next_match=0,
            goals=3.1, goals_missed=0.7, possession=66
        )
        dortmund = Club.objects.create(
            name='Боруссия Дортмунд', country='Германия', town='Дортмунд',
            price=800000000, founded=1909, stadium='Сигнал Идуна',
            match_1=0, match_2=0, match_3=0, match_4=0, match_5=0, next_match=0,
            goals=2.5, goals_missed=1.2, possession=59
        )
        leverkusen = Club.objects.create(
            name='Байер Леверкузен', country='Германия', town='Леверкузен',
            price=600000000, founded=1904, stadium='БайАрена',
            match_1=0, match_2=0, match_3=0, match_4=0, match_5=0, next_match=0,
            goals=2.4, goals_missed=1.0, possession=58
        )
        leipzig = Club.objects.create(
            name='РБ Лейпциг', country='Германия', town='Лейпциг',
            price=550000000, founded=2009, stadium='Ред Булл Арена',
            match_1=0, match_2=0, match_3=0, match_4=0, match_5=0, next_match=0,
            goals=2.3, goals_missed=1.3, possession=57
        )
        frankfurt = Club.objects.create(
            name='Айнтрахт Франкфурт', country='Германия', town='Франкфурт',
            price=400000000, founded=1899, stadium='Вальдштадион',
            match_1=0, match_2=0, match_3=0, match_4=0, match_5=0, next_match=0,
            goals=1.9, goals_missed=1.4, possession=52
        )
        gladbach = Club.objects.create(
            name='Боруссия Мёнхенгладбах', country='Германия', town='Мёнхенгладбах',
            price=350000000, founded=1900, stadium='Боруссия Парк',
            match_1=0, match_2=0, match_3=0, match_4=0, match_5=0, next_match=0,
            goals=1.7, goals_missed=1.5, possession=51
        )

        # ЛИГА 1
        print("   Создаем клубы Лиги 1...")
        psg = Club.objects.create(
            name='ПСЖ', country='Франция', town='Париж',
            price=950000000, founded=1970, stadium='Парк де Пренс',
            match_1=0, match_2=0, match_3=0, match_4=0, match_5=0, next_match=0,
            goals=2.9, goals_missed=0.8, possession=67
        )
        marseille = Club.objects.create(
            name='Марсель', country='Франция', town='Марсель',
            price=500000000, founded=1899, stadium='Велодром',
            match_1=0, match_2=0, match_3=0, match_4=0, match_5=0, next_match=0,
            goals=2.1, goals_missed=1.3, possession=55
        )
        lyon = Club.objects.create(
            name='Лион', country='Франция', town='Лион',
            price=450000000, founded=1950, stadium='Парк Олимпик',
            match_1=0, match_2=0, match_3=0, match_4=0, match_5=0, next_match=0,
            goals=1.9, goals_missed=1.4, possession=56
        )
        monaco = Club.objects.create(
            name='Монако', country='Франция', town='Монако',
            price=400000000, founded=1924, stadium='Луи II',
            match_1=0, match_2=0, match_3=0, match_4=0, match_5=0, next_match=0,
            goals=2.0, goals_missed=1.5, possession=54
        )
        nice = Club.objects.create(
            name='Ницца', country='Франция', town='Ницца',
            price=350000000, founded=1904, stadium='Альянц Ривьера',
            match_1=0, match_2=0, match_3=0, match_4=0, match_5=0, next_match=0,
            goals=1.6, goals_missed=0.9, possession=53
        )
        lille = Club.objects.create(
            name='Лилль', country='Франция', town='Лилль',
            price=380000000, founded=1944, stadium='Пьер Моруа',
            match_1=0, match_2=0, match_3=0, match_4=0, match_5=0, next_match=0,
            goals=1.8, goals_missed=1.1, possession=52
        )

        print(f"   Создано {Club.objects.count()} клубов")

        # Шаг 4: Группируем клубы по турнирам
        print("\n4. Группируем клубы по турнирам...")
        apl_clubs = [man_city, arsenal, liverpool, chelsea, man_united, tottenham]
        ll_clubs = [real_madrid, barcelona, atletico, sevilla, valencia, villarreal]
        sa_clubs = [inter, juventus, ac_milan, napoli, roma, lazio]
        bl_clubs = [bayern, dortmund, leverkusen, leipzig, frankfurt, gladbach]
        l1_clubs = [psg, marseille, lyon, monaco, nice, lille]

        # Шаг 5: Создаем пустую турнирную статистику
        print("\n5. Создаем начальную турнирную статистику...")
        
        def create_initial_stats(tournament, clubs):
            for club in clubs:
                TournamentClub.objects.create(
                    tournament=tournament,
                    club=club,
                    matches_played=0,
                    wins=0,
                    draws=0,
                    losses=0,
                    goals_for=0,
                    goals_against=0
                )
        
        create_initial_stats(tournament_apl, apl_clubs)
        create_initial_stats(tournament_ll, ll_clubs)
        create_initial_stats(tournament_sa, sa_clubs)
        create_initial_stats(tournament_bl, bl_clubs)
        create_initial_stats(tournament_l1, l1_clubs)
        
        print(f"   Создано {TournamentClub.objects.count()} турнирных записей")

        # Шаг 6: Создаем матчи
        print("\n6. Создаем матчи для каждого турнира...")
        
        def generate_matches_for_tournament(tournament, clubs, start_date):
            """Генерирует матчи для турнира (каждый с каждым)"""
            matches = []
            current_date = start_date
            
            for i in range(len(clubs)):
                for j in range(i + 1, len(clubs)):
                    home = clubs[i]
                    away = clubs[j]
                    
                    # Определяем статус (70% завершены, 30% запланированы)
                    is_finished = random.random() < 0.7
                    
                    if is_finished:
                        # Генерируем реалистичный счет
                        home_strength = home.goals
                        away_strength = away.goals
                        
                        # Более сильная команда имеет преимущество
                        home_advantage = random.uniform(0.8, 1.2)  # Домашнее преимущество
                        adjusted_home = home_strength * home_advantage
                        
                        # Генерируем голы на основе силы команд
                        home_goals = max(0, int(random.gauss(adjusted_home, 1.0)))
                        away_goals = max(0, int(random.gauss(away_strength, 1.0)))
                        
                        # Убедимся что не слишком много голов
                        home_goals = min(home_goals, 5)
                        away_goals = min(away_goals, 4)
                        
                        # Статистика матча
                        total_shots = random.randint(18, 30)
                        home_possession = home.possession
                        away_possession = 100 - home_possession
                        
                        home_shots = int(total_shots * (home_possession / 100))
                        away_shots = total_shots - home_shots
                        
                        home_shots_on_target = int(home_shots * random.uniform(0.3, 0.6))
                        away_shots_on_target = int(away_shots * random.uniform(0.3, 0.6))
                        
                        home_saves = max(0, away_shots_on_target - away_goals)
                        away_saves = max(0, home_shots_on_target - home_goals)
                        
                        home_red_cards = random.choices([0, 0, 0, 1], weights=[0.85, 0.10, 0.03, 0.02])[0]
                        away_red_cards = random.choices([0, 0, 0, 1], weights=[0.85, 0.10, 0.03, 0.02])[0]
                        
                        status = 'finished'
                    else:
                        # Запланированный матч
                        home_goals = 0
                        away_goals = 0
                        home_possession = 50
                        away_possession = 50
                        home_shots = 0
                        away_shots = 0
                        home_shots_on_target = 0
                        away_shots_on_target = 0
                        home_saves = 0
                        away_saves = 0
                        home_red_cards = 0
                        away_red_cards = 0
                        status = 'scheduled'
                    
                    match_data = {
                        'home_club': home,
                        'away_club': away,
                        'tournament': tournament,
                        'town': home.town,
                        'stadium': home.stadium,
                        'datetime': current_date,
                        'home_goals': home_goals,
                        'away_goals': away_goals,
                        'home_possession': home_possession,
                        'away_possession': away_possession,
                        'home_shots': home_shots,
                        'away_shots': away_shots,
                        'home_shots_on_target': home_shots_on_target,
                        'away_shots_on_target': away_shots_on_target,
                        'home_red_cards': home_red_cards,
                        'away_red_cards': away_red_cards,
                        'home_saves': home_saves,
                        'away_saves': away_saves,
                        'status': status
                    }
                    
                    matches.append(match_data)
                    current_date += timedelta(days=random.randint(2, 4))
            
            return matches

        # Генерируем матчи для каждого турнира
        print("   Генерируем матчи АПЛ...")
        apl_matches = generate_matches_for_tournament(
            tournament_apl, apl_clubs, datetime(2023, 8, 12, 15, 0)
        )
        
        print("   Генерируем матчи Ла Лиги...")
        ll_matches = generate_matches_for_tournament(
            tournament_ll, ll_clubs, datetime(2023, 8, 13, 17, 0)
        )
        
        print("   Генерируем матчи Серии А...")
        sa_matches = generate_matches_for_tournament(
            tournament_sa, sa_clubs, datetime(2023, 8, 19, 20, 45)
        )
        
        print("   Генерируем матчи Бундеслиги...")
        bl_matches = generate_matches_for_tournament(
            tournament_bl, bl_clubs, datetime(2023, 8, 18, 18, 30)
        )
        
        print("   Генерируем матчи Лиги 1...")
        l1_matches = generate_matches_for_tournament(
            tournament_l1, l1_clubs, datetime(2023, 8, 11, 21, 0)
        )

        # Сохраняем все матчи в базу
        print("\n7. Сохраняем матчи в базу данных...")
        all_matches = apl_matches + ll_matches + sa_matches + bl_matches + l1_matches
        
        for match_data in all_matches:
            Match.objects.create(**match_data)
        
        print(f"   Сохранено {Match.objects.count()} матчей")
        print(f"   Завершенных: {Match.objects.filter(status='finished').count()}")
        print(f"   Запланированных: {Match.objects.filter(status='scheduled').count()}")

        # Шаг 8: Обновляем турнирную статистику на основе матчей
        print("\n8. Обновляем турнирную статистику...")
        
        def update_tournament_statistics():
            # Обнуляем все статистики
            TournamentClub.objects.all().update(
                matches_played=0,
                wins=0,
                draws=0,
                losses=0,
                goals_for=0,
                goals_against=0
            )
            
            # Обрабатываем только завершенные матчи
            finished_matches = Match.objects.filter(status='finished')
            
            for match in finished_matches:
                try:
                    # Находим статистику для домашней команды
                    home_stat = TournamentClub.objects.get(
                        tournament=match.tournament,
                        club=match.home_club
                    )
                    
                    # Находим статистику для гостевой команды
                    away_stat = TournamentClub.objects.get(
                        tournament=match.tournament,
                        club=match.away_club
                    )
                    
                    # Обновляем статистику
                    home_stat.matches_played += 1
                    away_stat.matches_played += 1
                    
                    home_stat.goals_for += match.home_goals
                    home_stat.goals_against += match.away_goals
                    away_stat.goals_for += match.away_goals
                    away_stat.goals_against += match.home_goals
                    
                    if match.home_goals > match.away_goals:
                        home_stat.wins += 1
                        away_stat.losses += 1
                    elif match.home_goals < match.away_goals:
                        home_stat.losses += 1
                        away_stat.wins += 1
                    else:
                        home_stat.draws += 1
                        away_stat.draws += 1
                    
                    home_stat.save()
                    away_stat.save()
                    
                except (TournamentClub.DoesNotExist, Tournament.DoesNotExist) as e:
                    print(f"   Ошибка при обновлении матча {match}: {e}")
                    continue
        
        update_tournament_statistics()
        
        print(f"   Статистика обновлена для {TournamentClub.objects.count()} записей")

        # Шаг 9: Обновляем последние матчи клубов
        print("\n9. Обновляем последние матчи клубов...")
        
        def update_club_last_matches():
            all_clubs = Club.objects.all()
            
            for club in all_clubs:
                # Получаем последние 5 завершенных матчей
                home_matches = Match.objects.filter(
                    home_club=club,
                    status='finished'
                ).order_by('-datetime')[:5]
                
                away_matches = Match.objects.filter(
                    away_club=club,
                    status='finished'
                ).order_by('-datetime')[:5]
                
                # Объединяем и сортируем
                all_recent_matches = list(home_matches) + list(away_matches)
                all_recent_matches.sort(key=lambda x: x.datetime, reverse=True)
                last_5 = all_recent_matches[:5]
                
                # Обновляем поля match_1 - match_5
                for i, match in enumerate(last_5):
                    if i >= 5:
                        break
                    
                    # Определяем результат для этого клуба
                    if match.home_club == club:
                        if match.home_goals > match.away_goals:
                            result = 3  # победа
                        elif match.home_goals < match.away_goals:
                            result = 0  # поражение
                        else:
                            result = 1  # ничья
                    else:  # клуб в гостях
                        if match.away_goals > match.home_goals:
                            result = 3  # победа
                        elif match.away_goals < match.home_goals:
                            result = 0  # поражение
                        else:
                            result = 1  # ничья
                    
                    # Записываем в соответствующее поле
                    if i == 0:
                        club.match_1 = result
                    elif i == 1:
                        club.match_2 = result
                    elif i == 2:
                        club.match_3 = result
                    elif i == 3:
                        club.match_4 = result
                    elif i == 4:
                        club.match_5 = result
                
                # Обновляем next_match
                has_upcoming = Match.objects.filter(
                    Q(home_club=club) | Q(away_club=club),
                    status='scheduled',
                    datetime__gt=datetime.now()
                ).exists()
                
                club.next_match = 1 if has_upcoming else 0
                club.save()
        
        update_club_last_matches()
        print("   Последние матчи обновлены")

        # Шаг 10: Финальный отчет
        print("\n" + "=" * 60)
        print("ЗАГРУЗКА ДАННЫХ ЗАВЕРШЕНА!")
        print("=" * 60)
        
        print(f"\nИТОГОВАЯ СТАТИСТИКА:")
        print(f"Турниров: {Tournament.objects.count()}")
        print(f"Клубов: {Club.objects.count()}")
        print(f"Матчей всего: {Match.objects.count()}")
        print(f"  • Завершено: {Match.objects.filter(status='finished').count()}")
        print(f"  • Запланировано: {Match.objects.filter(status='scheduled').count()}")
        print(f"Турнирных записей: {TournamentClub.objects.count()}")
        
        # Статистика по турнирам
        print(f"\nСТАТИСТИКА ПО ТУРНИРАМ:")
        for tournament in Tournament.objects.all():
            clubs_count = tournament.clubs.count()
            matches_count = Match.objects.filter(tournament=tournament).count()
            finished_count = Match.objects.filter(tournament=tournament, status='finished').count()
            print(f"  {tournament.name}:")
            print(f"    Клубов: {clubs_count}")
            print(f"    Матчей: {matches_count} ({finished_count} завершено)")
        
        return True



def home(request): 
    # load_tournament_data()
    
    """
    Главная страница с поиском клубов, матчей и турниров
    """
    # Поиск клубов
    club_query = request.GET.get('club_q', '')
    if club_query:
        clubs = Club.objects.filter(
            Q(name__icontains=club_query) |
            Q(country__icontains=club_query)
        )
    else:
        clubs = Club.objects.all()

    # Поиск матчей
    match_query_home = request.GET.get('match_home', '')
    match_query_away = request.GET.get('match_away', '')
    
    matches = Match.objects.all().order_by('-datetime')
    
    if match_query_home:
        matches = matches.filter(home_club__name__icontains=match_query_home)
    
    if match_query_away:
        matches = matches.filter(away_club__name__icontains=match_query_away)

    # Поиск турниров
    tournament_query = request.GET.get('tournament_q', '')
    if tournament_query:
        tournaments = Tournament.objects.filter(
            Q(name__icontains=tournament_query) |
            Q(country__icontains=tournament_query)
        ).annotate(
            participants_count_annotated=Count('clubs', distinct=True),  # ИЗМЕНЕНО
            matches_count=Count('matches', distinct=True)
        ).order_by('name')
    else:
        # Показываем только топ-5 турниров по умолчанию
        tournaments = Tournament.objects.annotate(
            participants_count_annotated=Count('clubs', distinct=True),  # ИЗМЕНЕНО
            matches_count=Count('matches', distinct=True)
        ).order_by('name')[:5]

    context = {
        'title': 'Главная страница',
        'clubs': clubs,
        'matches': matches,
        'tournaments': tournaments,
        'club_query': club_query,
        'match_query_home': match_query_home,
        'match_query_away': match_query_away,
        'tournament_query': tournament_query,
    }
    return render(request, 'main/home.html', context)

def club(request, club_id):
    """
    Детальная страница клуба
    """
    club = get_object_or_404(Club, id=club_id)

    last_matches = club.get_last_match_objects()

    context = {
        'title': f'{club.name} - Детальная информация',
        'club': club,
        'last_matches': last_matches,
    }
    return render(request, 'main/club.html', context)

def tournament(request):
    context = {'title': 'Информация о турнире'}
    return render(request, 'main/tournament.html', context)




def match(request, match_id):
    """
    Детальная страница матча
    """
    match = get_object_or_404(Match, id=match_id)
    
    # Определяем победителя
    winner = None
    if match.status == 'finished':
        if match.home_goals > match.away_goals:
            winner = match.home_club
        elif match.home_goals < match.away_goals:
            winner = match.away_club
        else:
            winner = 'draw'  # ничья
    
    # Собираем основную статистику
    total_shots = match.home_shots + match.away_shots
    total_shots_on_target = match.home_shots_on_target + match.away_shots_on_target
    total_corners = match.home_corners + match.away_corners if hasattr(match, 'home_corners') else 0
    
    # Проверяем наличие дополнительных полей
    has_corners = hasattr(match, 'home_corners') and hasattr(match, 'away_corners')
    has_fouls = hasattr(match, 'home_fouls') and hasattr(match, 'away_fouls')
    
    context = {
        'title': f'{match.home_club.name} vs {match.away_club.name}',
        'match': match,
        'winner': winner,
        'total_shots': total_shots,
        'total_shots_on_target': total_shots_on_target,
        'total_corners': total_corners,
        'has_corners': has_corners,
        'has_fouls': has_fouls,
    }
    context.update(frontend_service_urls())
    return render(request, 'main/match.html', context)


def match_ticketing_info(request, match_id):
    match = get_object_or_404(
        Match.objects.select_related('home_club', 'away_club', 'tournament'),
        id=match_id,
    )
    return JsonResponse({
        'match_id': match.id,
        'home_club': match.home_club.name,
        'away_club': match.away_club.name,
        'tournament': match.tournament.name if match.tournament else None,
        'datetime': match.datetime.isoformat(),
        'status': match.status,
        'seats_available': match.seats_available,
        'price': str(match.price),
        'currency': 'RUB',
    })


def auth_page(request):
    next_url = (request.GET.get("next") or "/").strip() or "/"
    context = {
        "title": "Вход и регистрация",
        "next_url": next_url,
    }
    context.update(frontend_service_urls())
    return render(request, "main/auth.html", context)


def cart_page(request):
    context = {
        "title": "Корзина",
    }
    context.update(frontend_service_urls())
    return render(request, "main/cart.html", context)












def tournament(request, tournament_id):
    """
    Детальная страница турнира (простая версия)
    """
    tournament = get_object_or_404(Tournament, id=tournament_id)
    
    # Получаем таблицу участников С БАЗОВОЙ СОРТИРОВКОЙ
    # Не используем свойства @property для сортировки!
    participants = TournamentClub.objects.filter(
        tournament=tournament
    ).select_related('club').annotate(
        # Добавляем вычисляемые поля для сортировки
        points_calc=F('wins') * 3 + F('draws'),
        goal_diff=F('goals_for') - F('goals_against')
    ).order_by('-points_calc', '-goal_diff', '-goals_for')
    
    # Получаем матчи турнира
    matches = Match.objects.filter(
        tournament=tournament
    ).select_related('home_club', 'away_club').order_by('-datetime')
    
    # Базовая статистика
    tournament_stats = {
        'total_participants': participants.count(),
        'total_matches': matches.filter(status='finished').count(),
        'total_goals': matches.filter(status='finished').aggregate(
            total=Sum(F('home_goals') + F('away_goals'))
        )['total'] or 0,
    }
    
    if tournament_stats['total_matches'] > 0:
        tournament_stats['avg_goals_per_match'] = round(
            tournament_stats['total_goals'] / tournament_stats['total_matches'], 
            2
        )
    
    context = {
        'title': tournament.name,
        'tournament': tournament,
        'participants': participants,
        'matches': matches,
        'tournament_stats': tournament_stats,
    }
    return render(request, 'main/tournament.html', context)
