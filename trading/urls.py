from django.urls import path

from . import views

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("strategies/", views.strategies_page, name="strategies"),
    path("backtest/", views.backtest_page, name="backtest"),
    path("set-strategy/", views.set_strategy, name="set_strategy"),
    path("tick/", views.tick, name="tick"),
    path("reset/", views.reset_portfolio, name="reset"),
    path("trade/", views.manual_trade, name="manual_trade"),
]
