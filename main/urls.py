from django.urls import path
from . import views


urlpatterns = [
    path('metrics', views.metrics_view, name='metrics'),
    path('', views.home, name='home'),
    path('auth/', views.auth_page, name='auth_page'),
    path('cart/', views.cart_page, name='cart_page'),
    path('tournament/', views.tournament, name='tournament'),
    path('club/<int:club_id>/', views.club, name='club'),
    path('match/<int:match_id>/', views.match, name='match'),
    path('api/matches/<int:match_id>/ticketing/', views.match_ticketing_info, name='match_ticketing_info'),
    path('tournament/<int:tournament_id>/', views.tournament, name='tournament'),

]
