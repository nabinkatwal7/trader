from django import forms
from django.conf import settings

from .strategies import list_strategies


def _strategy_choices():
    return [(s.key, s.name) for s in list_strategies()]


class BacktestForm(forms.Form):
    strategy = forms.ChoiceField(choices=_strategy_choices)
    symbols = forms.CharField(
        initial=",".join(settings.DEFAULT_SYMBOLS),
        help_text="Comma-separated tickers, e.g. AAPL,MSFT,NVDA",
    )
    days = forms.IntegerField(min_value=30, max_value=365, initial=90)
    cash = forms.FloatField(min_value=100, initial=settings.STARTING_CASH)


class StrategySelectForm(forms.Form):
    strategy = forms.ChoiceField(choices=_strategy_choices)


class ManualTradeForm(forms.Form):
    action = forms.ChoiceField(choices=[("buy", "Buy $"), ("sell", "Sell shares")])
    symbol = forms.CharField(max_length=16)
    amount = forms.FloatField(min_value=0.0001, help_text="Dollars for buy, shares for sell")
