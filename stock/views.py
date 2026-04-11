from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.core.cache import cache
from decimal import Decimal
from django.contrib import messages

from stock.models import Stock, AccountCurrency, AccountStock
from stock.forms import BuySellForm, SellForm

def stock_list(request):
    stocks = Stock.objects.all()
    context = {
        'stocks': stocks,
    }
    return render(request, 'stocks.html', context)

@login_required
def stock_detail(request, pk):
    stock = get_object_or_404(Stock, pk=pk)
    context = {
        'stock': stock,
        'form': BuySellForm(initial={'price': stock.get_random_price()})
    }
    return render(request, 'stock.html', context)

@login_required
def stock_buy(request, pk):
    if request.method != "POST":
        return redirect('stock:detail', pk=pk)

    stock = get_object_or_404(Stock, pk=pk)
    form = BuySellForm(request.POST)

    if form.is_valid():
        amount = form.cleaned_data['amount']
        price = form.cleaned_data['price']
        buy_cost = Decimal(str(price)) * Decimal(str(amount))

        acc_stock, created = AccountStock.objects.get_or_create(
            account=request.user.account,
            stock=stock,
            defaults={'average_buy_cost': 0, 'amount': 0}
        )
        
        if acc_stock.amount == 0:
            acc_stock.average_buy_cost = price
            acc_stock.amount = amount
        else:
            total_cost = acc_stock.average_buy_cost * acc_stock.amount + buy_cost
            total_amount = acc_stock.amount + amount
            acc_stock.average_buy_cost = total_cost / total_amount
            acc_stock.amount = total_amount

        acc_currency, created = AccountCurrency.objects.get_or_create(
            account=request.user.account,
            currency=stock.currency,
            defaults={'amount': 0}
        )

        if acc_currency.amount < buy_cost:
            messages.error(request, f'На счёте недостаточно средств в валюте {stock.currency.sign}')
        else:
            acc_currency.amount -= buy_cost
            acc_stock.save()
            acc_currency.save()
            
            cache.delete(f'currencies_{request.user.username}')
            cache.delete(f'stocks_{request.user.username}')
            
            messages.success(request, f'Вы купили {amount} акций {stock.ticker} на сумму {buy_cost}{stock.currency.sign}')
            return redirect('stock:account')

    context = {
        'stock': get_object_or_404(Stock, pk=pk),
        'form': form
    }

    return render(request, 'stock.html', context)

@login_required
def stock_sell(request, pk):
    if request.method != "POST":
        return redirect('stock:detail', pk=pk)

    stock = get_object_or_404(Stock, pk=pk)
    form = SellForm(request.POST)

    if form.is_valid():
        amount = form.cleaned_data['amount']
        price = form.cleaned_data['price']
        sell_value = Decimal(str(price)) * Decimal(str(amount))

        try:
            acc_stock = AccountStock.objects.get(account=request.user.account, stock=stock)
        except AccountStock.DoesNotExist:
            messages.error(request, 'У вас нет этих акций')
            context = {'stock': stock, 'form': form}
            return render(request, 'stock.html', context)

        if acc_stock.amount < amount:
            messages.error(request, f'У вас недостаточно акций {stock.ticker}. Доступно: {acc_stock.amount}')
        else:
            acc_stock.amount -= amount

            if acc_stock.amount == 0:
                acc_stock.average_buy_cost = 0
            acc_stock.save()

            acc_currency, created = AccountCurrency.objects.get_or_create(
                account=request.user.account,
                currency=stock.currency,
                defaults={'amount': 0}
            )
            acc_currency.amount += sell_value
            acc_currency.save()
            
            cache.delete(f'currencies_{request.user.username}')
            cache.delete(f'stocks_{request.user.username}')
            
            messages.success(request, f'Вы продали {amount} акций {stock.ticker} на сумму {sell_value}{stock.currency.sign}')
            return redirect('stock:account')

    context = {
        'stock': get_object_or_404(Stock, pk=pk),
        'form': form,
        'sell_mode': True
    }

    return render(request, 'stock.html', context)

@login_required
def account(request):    
    currencies = cache.get(f'currencies_{request.user.username}')
    stocks = cache.get(f'stocks_{request.user.username}')

    if currencies is None:
        currencies = [
            {
                'amount': acc_currency.amount,
                'sign': acc_currency.currency.sign,
                'currency_sign': acc_currency.currency.sign,
            } for acc_currency in request.user.account.accountcurrency_set.select_related('currency')
        ]
        cache.set(f'currencies_{request.user.username}', currencies, 300)

    if stocks is None:
        stocks_data = []
        for acc_stock in request.user.account.accountstock_set.select_related('stock', 'stock__currency'):
            current_price = acc_stock.stock.get_random_price()
            total_current_value = current_price * acc_stock.amount
            total_buy_value = float(acc_stock.average_buy_cost) * acc_stock.amount if acc_stock.average_buy_cost else 0
            profit_loss = total_current_value - total_buy_value
            
            stocks_data.append({
                'ticker': acc_stock.stock.ticker,
                'amount': acc_stock.amount,
                'avg': float(acc_stock.average_buy_cost) if acc_stock.average_buy_cost else 0,
                'pk': acc_stock.stock.pk,
                'current_price': current_price,
                'profit_loss': round(profit_loss, 2),
                'currency_sign': acc_stock.stock.currency.sign if acc_stock.stock.currency else '$',
            })
        stocks = stocks_data
        cache.set(f'stocks_{request.user.username}', stocks, 300)

    context = {
        'currencies': currencies,
        'stocks': stocks
    }

    return render(request, 'account.html', context=context)