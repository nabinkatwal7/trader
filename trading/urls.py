from django.urls import path

from . import views

urlpatterns = [
    path("login/", views.UserLoginView.as_view(), name="login"),
    path("logout/", views.UserLogoutView.as_view(), name="logout"),
    path("signup/", views.signup, name="signup"),
    path("", views.dashboard, name="dashboard"),
    path("markets/", views.markets_page, name="markets"),
    path("analytics/", views.analytics_page, name="analytics"),
    path("blotter/", views.blotter_page, name="blotter"),
    path("blotter/export/", views.export_trades, name="export_trades"),
    path("journal/", views.journal_page, name="journal"),
    path("journal/<int:pk>/delete/", views.journal_delete, name="journal_delete"),
    path("strategies/", views.strategies_page, name="strategies"),
    path("backtest/", views.backtest_page, name="backtest"),
    path("compare/", views.compare_page, name="compare"),
    path("leaderboard/", views.leaderboard_page, name="leaderboard"),
    path("settings/", views.settings_page, name="settings"),
    path("set-strategy/", views.set_strategy, name="set_strategy"),
    path("set-watch/", views.set_watch, name="set_watch"),
    path("tick/", views.tick, name="tick"),
    path("reset/", views.reset_portfolio, name="reset"),
    path("trade/", views.manual_trade, name="manual_trade"),
    path("watchlist/add/", views.watchlist_add, name="watchlist_add"),
    path("watchlist/<str:symbol>/remove/", views.watchlist_remove, name="watchlist_remove"),
    path("alerts/add/", views.alert_add, name="alert_add"),
    path("alerts/<int:pk>/delete/", views.alert_delete, name="alert_delete"),
    path("api/ohlc/", views.api_ohlc, name="api_ohlc"),
    path("api/backtest/<int:pk>/chart/", views.api_backtest_chart, name="api_backtest_chart"),
]
