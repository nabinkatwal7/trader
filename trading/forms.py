from django import forms
from django.conf import settings
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.contrib.auth.models import User

from .strategies import list_strategies


def _strategy_choices():
    return [(s.key, s.name) for s in list_strategies()]


class LoginForm(AuthenticationForm):
    username = forms.CharField(widget=forms.TextInput(attrs={"autocomplete": "username", "placeholder": "username"}))
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={"autocomplete": "current-password", "placeholder": "password"})
    )


class SignUpForm(UserCreationForm):
    class Meta:
        model = User
        fields = ("username", "password1", "password2")


class BacktestForm(forms.Form):
    strategy = forms.ChoiceField(choices=_strategy_choices)
    symbols = forms.CharField(
        initial=",".join(settings.DEFAULT_SYMBOLS),
        help_text="Comma-separated tickers",
    )
    days = forms.IntegerField(min_value=30, max_value=365, initial=90)
    cash = forms.FloatField(min_value=100, initial=settings.STARTING_CASH)


class CompareForm(forms.Form):
    strategies = forms.MultipleChoiceField(
        choices=_strategy_choices,
        widget=forms.CheckboxSelectMultiple,
        help_text="Pick 2–8 strategies to race",
    )
    symbols = forms.CharField(initial="AAPL,MSFT,NVDA")
    days = forms.IntegerField(min_value=30, max_value=365, initial=90)
    cash = forms.FloatField(min_value=100, initial=settings.STARTING_CASH)

    def clean_strategies(self):
        picked = self.cleaned_data["strategies"]
        if len(picked) < 2:
            raise forms.ValidationError("Select at least two strategies.")
        if len(picked) > 8:
            raise forms.ValidationError("Max 8 strategies.")
        return picked


class StrategySelectForm(forms.Form):
    strategy = forms.ChoiceField(choices=_strategy_choices)


class ManualTradeForm(forms.Form):
    action = forms.ChoiceField(choices=[("buy", "Buy $"), ("sell", "Sell shares")])
    symbol = forms.CharField(max_length=16)
    amount = forms.FloatField(min_value=0.0001)
    note = forms.CharField(max_length=200, required=False)


class WatchSymbolForm(forms.Form):
    symbol = forms.CharField(max_length=16, initial="AAPL")


class WatchlistAddForm(forms.Form):
    symbol = forms.CharField(max_length=16)


class JournalForm(forms.Form):
    title = forms.CharField(max_length=120)
    body = forms.CharField(widget=forms.Textarea(attrs={"rows": 4}))
    symbol = forms.CharField(max_length=16, required=False)
    mood = forms.ChoiceField(
        choices=[
            ("neutral", "Neutral"),
            ("confident", "Confident"),
            ("cautious", "Cautious"),
            ("fomo", "FOMO"),
            ("lesson", "Lesson learned"),
        ]
    )


class AlertForm(forms.Form):
    symbol = forms.CharField(max_length=16)
    direction = forms.ChoiceField(choices=[("above", "Above"), ("below", "Below")])
    target = forms.FloatField(min_value=0.01)


class SettingsForm(forms.Form):
    fee_bps = forms.FloatField(
        min_value=0,
        max_value=100,
        initial=0,
        help_text="Commission in basis points (10 = 0.10% per trade)",
    )
    starting_cash = forms.FloatField(min_value=100, max_value=1_000_000)
    active_strategy = forms.ChoiceField(choices=_strategy_choices)
    chart_range = forms.ChoiceField(
        choices=[("30", "1M"), ("90", "3M"), ("180", "6M"), ("365", "1Y")],
    )


class BlotterFilterForm(forms.Form):
    symbol = forms.CharField(required=False, max_length=16)
    action = forms.ChoiceField(
        required=False,
        choices=[("", "All"), ("BUY", "Buy"), ("SELL", "Sell")],
    )
