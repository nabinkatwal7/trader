from django.urls import path

from . import views

urlpatterns = [
    path("login/", views.UserLoginView.as_view(), name="login"),
    path("logout/", views.UserLogoutView.as_view(), name="logout"),
    path("signup/", views.signup, name="signup"),
    path("", views.dashboard, name="dashboard"),
    path("strategies/", views.strategies_page, name="strategies"),
    path("backtest/", views.backtest_page, name="backtest"),
    path("set-strategy/", views.set_strategy, name="set_strategy"),
    path("set-watch/", views.set_watch, name="set_watch"),
    path("tick/", views.tick, name="tick"),
    path("reset/", views.reset_portfolio, name="reset"),
    path("trade/", views.manual_trade, name="manual_trade"),
    path("api/ohlc/", views.api_ohlc, name="api_ohlc"),
    path("api/backtest/<int:pk>/chart/", views.api_backtest_chart, name="api_backtest_chart"),
]
