from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator
from django.db.models import Q, F
from django.utils.text import slugify
from decimal import Decimal
import os

class Club(models.Model):
    name = models.CharField(
        max_length=255, 
        verbose_name='Название клуба'
    )
    country = models.CharField(
        max_length=100, 
        verbose_name='Страна'
    )
    town = models.CharField(
        max_length=100, 
        verbose_name='Город'
    )
    price = models.IntegerField(
        verbose_name='Цена',
        validators=[MinValueValidator(0)]
    )
    
    def emblem_upload_path(instance, filename):
        # Создаем путь для загрузки: clubs/название-клуба/emblem.ext
        name = slugify(instance.name)
        ext = filename.split('.')[-1]
        return f'clubs/{name}/emblem.{ext}'
    
    emblem = models.ImageField(
        upload_to=emblem_upload_path,
        verbose_name='Эмблема',
        blank=True,
        null=True
    )
    emblem_url = models.URLField(
        verbose_name='Эмблема (URL)',
        blank=True
    )
    founded = models.IntegerField(
        verbose_name='Год основания'
    )
    stadium = models.CharField(
        max_length=255,
        verbose_name='Стадион'
    )
    match_1 = models.IntegerField(
        verbose_name='Прошлый матч',
        default=0
    )
    match_2 = models.IntegerField(
        verbose_name='Позапрошлый матч',
        default=0
    )
    match_3 = models.IntegerField(
        verbose_name='Позапозапрошлый матч',
        default=0
    )
    match_4 = models.IntegerField(
        verbose_name='Позапозапозапрошлый матч',
        default=0
    )
    match_5 = models.IntegerField(
        verbose_name='Позапозапозапозапрошлый матч',
        default=0
    )
    next_match = models.IntegerField(
        verbose_name='Следующий матч',
        default=0
    )
    goals = models.FloatField(
        verbose_name='Забито в среднем',
        default=0.0,
        validators=[MinValueValidator(0.0)]
    )
    goals_missed = models.FloatField(
        verbose_name='Пропущено в среднем',
        default=0.0,
        validators=[MinValueValidator(0.0)]
    )
    possession = models.IntegerField(
        verbose_name='Среднее владение',
        default=0,
        validators=[MinValueValidator(0), MaxValueValidator(100)]
    )

    class Meta:
        verbose_name = 'Клуб'
        verbose_name_plural = 'Клубы'
        ordering = ['name']

    def __str__(self):
        return f"{self.name} ({self.country})"

    @property
    def emblem_src(self):
        if self.emblem:
            return self.emblem.url
        return self.emblem_url or ""

    def get_last_matches(self):
        """Возвращает последние 5 матчей"""
        return [self.match_1, self.match_2, self.match_3, self.match_4, self.match_5]
    
    def get_last_match_objects(self):
        """Возвращает последние 5 завершенных матчей в виде объектов Match"""
        home_matches = self.home_matches.filter(status='finished').order_by('-datetime')
        away_matches = self.away_matches.filter(status='finished').order_by('-datetime')
        
        from itertools import chain
        all_matches = sorted(
            chain(home_matches, away_matches),
            key=lambda x: x.datetime,
            reverse=True
        )
        
        return all_matches[:5]


class Tournament(models.Model):
    """Модель для самого турнира/чемпионата"""
    name = models.CharField(
        max_length=255,
        verbose_name='Название турнира',
        unique=True
    )
    
    # Страна проведения
    country = models.CharField(
        max_length=100,
        verbose_name='Страна проведения',
        blank=True
    )
    
    # Логотип
    def logo_upload_path(instance, filename):
        name = slugify(instance.name)
        ext = filename.split('.')[-1]
        return f'tournaments/{name}/logo.{ext}'
    
    logo = models.ImageField(
        upload_to=logo_upload_path,
        verbose_name='Логотип',
        blank=True,
        null=True
    )
    logo_url = models.URLField(
        verbose_name='Логотип (URL)',
        blank=True
    )
    
    # Связь с клубами через промежуточную модель
    clubs = models.ManyToManyField(
        Club,
        through='TournamentClub',
        related_name='tournaments',
        verbose_name='Клубы-участники'
    )
    
    class Meta:
        verbose_name = 'Турнир'
        verbose_name_plural = 'Турниры'
        ordering = ['name']
    
    def __str__(self):
        return f"{self.name}"

    @property
    def logo_src(self):
        if self.logo:
            return self.logo.url
        return self.logo_url or ""
    
    @property
    def participants_count(self):
        """Количество участников"""
        return self.clubs.count()


class TournamentClub(models.Model):
    """Связь клуба с турниром и его статистика в этом турнире"""
    tournament = models.ForeignKey(
        Tournament,
        on_delete=models.CASCADE,
        related_name='tournament_clubs',
        verbose_name='Турнир'
    )
    
    club = models.ForeignKey(
        Club,
        on_delete=models.CASCADE,
        related_name='tournament_participations',
        verbose_name='Клуб'
    )
    
    # Статистика в турнире
    matches_played = models.IntegerField(
        verbose_name='Сыграно матчей',
        default=0,
        validators=[MinValueValidator(0)]
    )
    
    wins = models.IntegerField(
        verbose_name='Победы',
        default=0,
        validators=[MinValueValidator(0)]
    )
    
    draws = models.IntegerField(
        verbose_name='Ничьи',
        default=0,
        validators=[MinValueValidator(0)]
    )
    
    losses = models.IntegerField(
        verbose_name='Поражения',
        default=0,
        validators=[MinValueValidator(0)]
    )
    
    goals_for = models.IntegerField(
        verbose_name='Забитые голы',
        default=0,
        validators=[MinValueValidator(0)]
    )
    
    goals_against = models.IntegerField(
        verbose_name='Пропущенные голы',
        default=0,
        validators=[MinValueValidator(0)]
    )
    
    
    class Meta:
        verbose_name = 'Участник турнира'
        verbose_name_plural = 'Участники турниров'
        unique_together = ['tournament', 'club']
        ordering = ['tournament', '-goals_for']
    
    def __str__(self):
        return f"{self.club.name} в {self.tournament.name}"
    
    # Расчетные свойства
    @property
    def points(self):
        """Очки (3 за победу, 1 за ничью)"""
        return self.wins * 3 + self.draws
    
    @property
    def goal_difference(self):
        """Разница мячей"""
        return self.goals_for - self.goals_against
    
    @property
    def win_percentage(self):
        """Процент побед"""
        if self.matches_played > 0:
            return round((self.wins / self.matches_played) * 100, 1)
        return 0.0


class Match(models.Model):
    # Основная информация о матче
    home_club = models.ForeignKey(
        Club,
        on_delete=models.PROTECT,
        related_name='home_matches',
        verbose_name='Хозяева'
    )
    away_club = models.ForeignKey(
        Club,
        on_delete=models.PROTECT,
        related_name='away_matches',
        verbose_name='Гости'
    )
    
    # Связь с турниром
    tournament = models.ForeignKey(
        Tournament,
        on_delete=models.SET_NULL,
        related_name='matches',
        verbose_name='Турнир',
        null=True,
        blank=True
    )
    
    # Остальные поля
    town = models.CharField(
        max_length=100,
        verbose_name='Город'
    )
    stadium = models.CharField(
        max_length=255,
        verbose_name='Стадион'
    )
    datetime = models.DateTimeField(
        verbose_name='Дата и время начала'
    )
    seats_available = models.IntegerField(
        verbose_name='Доступно мест',
        default=10000,
        validators=[MinValueValidator(0)]
    )
    price = models.DecimalField(
        verbose_name='Цена билета',
        max_digits=10,
        decimal_places=2,
        default=Decimal("1500.00"),
        validators=[MinValueValidator(0)]
    )
    
    # Результат матча
    home_goals = models.IntegerField(
        verbose_name='Голы хозяев',
        default=0,
        validators=[MinValueValidator(0)]
    )
    away_goals = models.IntegerField(
        verbose_name='Голы гостей',
        default=0,
        validators=[MinValueValidator(0)]
    )
    
    # Основная статистика
    home_possession = models.IntegerField(
        verbose_name='Владение хозяев (%)',
        default=50,
        validators=[MinValueValidator(0), MaxValueValidator(100)]
    )
    away_possession = models.IntegerField(
        verbose_name='Владение гостей (%)',
        default=50,
        validators=[MinValueValidator(0), MaxValueValidator(100)]
    )
    
    # Удары
    home_shots = models.IntegerField(
        verbose_name='Удары хозяев',
        default=0,
        validators=[MinValueValidator(0)]
    )
    away_shots = models.IntegerField(
        verbose_name='Удары гостей',
        default=0,
        validators=[MinValueValidator(0)]
    )
    
    home_shots_on_target = models.IntegerField(
        verbose_name='Удары в створ хозяев',
        default=0,
        validators=[MinValueValidator(0)]
    )
    away_shots_on_target = models.IntegerField(
        verbose_name='Удары в створ гостей',
        default=0,
        validators=[MinValueValidator(0)]
    )
    
    home_red_cards = models.IntegerField(
        verbose_name='Красные карточки хозяев',
        default=0,
        validators=[MinValueValidator(0)]
    )
    away_red_cards = models.IntegerField(
        verbose_name='Красные карточки гостей',
        default=0,
        validators=[MinValueValidator(0)]
    )
    
    # Сейвы вратарей
    home_saves = models.IntegerField(
        verbose_name='Сейвы хозяев',
        default=0,
        validators=[MinValueValidator(0)]
    )
    away_saves = models.IntegerField(
        verbose_name='Сейвы гостей',
        default=0,
        validators=[MinValueValidator(0)]
    )
    
    # Статус матча
    STATUS_CHOICES = [
        ('scheduled', 'Запланирован'),
        ('finished', 'Завершен'),
    ]
    
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='scheduled',
        verbose_name='Статус матча'
    )

    class Meta:
        verbose_name = 'Матч'
        verbose_name_plural = 'Матчи'
        ordering = ['-datetime']
        indexes = [
            models.Index(fields=['datetime']),
            models.Index(fields=['home_club', 'away_club']),
            models.Index(fields=['status']),
            models.Index(fields=['tournament']),
        ]
        constraints = [
            models.CheckConstraint(
                condition=~Q(home_club=F('away_club')),
                name='prevent_self_match'
            )
        ]

    def __str__(self):
        return f"{self.home_club.name} vs {self.away_club.name} - {self.datetime.strftime('%d.%m.%Y %H:%M')}"
