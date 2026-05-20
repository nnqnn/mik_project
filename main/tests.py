from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import Club, Match, Tournament


class MonitoringAndTicketingTests(TestCase):
    def setUp(self):
        self.home_club = Club.objects.create(
            name="Arsenal",
            country="England",
            town="London",
            price=900000000,
            founded=1886,
            stadium="Emirates",
        )
        self.away_club = Club.objects.create(
            name="Barcelona",
            country="Spain",
            town="Barcelona",
            price=1100000000,
            founded=1899,
            stadium="Camp Nou",
        )
        self.tournament = Tournament.objects.create(name="Champions League", country="Europe")
        self.match = Match.objects.create(
            home_club=self.home_club,
            away_club=self.away_club,
            tournament=self.tournament,
            town="London",
            stadium="Emirates",
            datetime=timezone.now(),
            seats_available=250,
            price=Decimal("1999.50"),
            status="scheduled",
        )

    def test_match_ticketing_info_endpoint(self):
        response = self.client.get(
            reverse("match_ticketing_info", kwargs={"match_id": self.match.id})
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["match_id"], self.match.id)
        self.assertEqual(response.json()["seats_available"], 250)
        self.assertEqual(response.json()["price"], "1999.50")
        self.assertEqual(response.json()["currency"], "RUB")

    def test_metrics_endpoint(self):
        self.client.get(reverse("match_ticketing_info", kwargs={"match_id": self.match.id}))

        response = self.client.get(reverse("metrics"))

        self.assertEqual(response.status_code, 200)
        self.assertIn("text/plain", response["Content-Type"])
        body = response.content.decode()
        self.assertIn("mik_http_requests_total", body)
        self.assertIn("mik_http_request_duration_seconds", body)
        self.assertIn("mik_domain_events_total", body)
