from django.contrib import messages, auth
from django.core.urlresolvers import reverse
from django.shortcuts import render, redirect, HttpResponseRedirect
from django.contrib.auth.decorators import login_required
from accounts.forms import UserRegistrationForm, UserLoginForm, SubscribeForm
from django.template.context_processors import csrf
import stripe
from django.conf import settings
from django.utils import timezone
import arrow
from django.views.decorators.csrf import csrf_exempt
import json
from django.contrib.auth.models import User
from django.http import HttpResponse
from .models import UserProfile


stripe.api_key = settings.STRIPE_SECRET

# Create your views here.
def logout(request):
    auth.logout(request)
    messages.success(request, 'You have successfully logged out')
    return redirect(reverse('index'))


@login_required(login_url='/accounts/login')
def profile(request):
    return render(request, 'profile.html')


def login(request):
    if request.method == 'POST':
        form = UserLoginForm(request.POST)
        if form.is_valid():
            user = auth.authenticate(username=request.POST.get('username_or_email'),
                                     password=request.POST.get('password'))

            if user is not None:
                auth.login(request, user)
                messages.error(request, "You have successfully logged in")

                if request.GET and 'next' in request.GET:
                    next = request.GET['next']
                    return HttpResponseRedirect(next)
                else:
                    return redirect(reverse('profile'))
            else:
                form.add_error(None, "Your username or password was not recognised")

    else:
        form = UserLoginForm()

    args = {'form': form, 'next': request.GET['next'] if request.GET and 'next' in request.GET else ''}
    args.update(csrf(request))
    return render(request, 'login.html', args)


def register(request):
    if request.method == 'POST':
        form = UserRegistrationForm(request.POST)
        if form.is_valid():
            form.save()

            user = auth.authenticate(username=request.POST.get('username'),
                                     password=request.POST.get('password1'))

            if user:
                auth.login(request, user)
                messages.success(request, "You have successfully registered")
                return redirect(reverse('profile'))

            else:
                messages.error(request, "unable to log you in at this time!")

    else:
        form = UserRegistrationForm()

    args = {'form': form}
    args.update(csrf(request))

    return render(request, 'register.html', args)


def subscribe(request):
    if request.method == 'POST':
        form = SubscribeForm(request.POST)
        if form.is_valid():
            try:
                customer = stripe.Customer.create(
                    email=request.user.email,
                    card=form.cleaned_data['stripe_id'],
                    plan='REG_MONTHLY',
                )

                if customer:
                    request.user.profile.stripe_id = customer.id
                    request.user.profile.subscription_end = arrow.now().replace(weeks=+4).datetime
                    request.user.save()

            except (stripe.error.CardError, ):
                messages.error(request, "Your card was declined!")

            messages.success(request, "You have successfully paid")
            return redirect(reverse('profile'))
        else:
            messages.error(request, "We were unable to take a payment with that card!")

    else:
        form = SubscribeForm

    args = {'form': form, 'publishable': settings.STRIPE_PUBLISHABLE}
    args.update(csrf(request))
    return render(request, 'subscribe.html', args)



@login_required(login_url='/accounts/login')
def cancel_subscription(request):
   try:
       customer = stripe.Customer.retrieve(request.user.profile.stripe_id)
       customer.cancel_subscription(at_period_end=False)
       request.user.profile.subscription_end = timezone.now()
       request.user.profile.save()
   except (Exception, e):
       messages.error(request, e)
   return redirect('profile')


@csrf_exempt
def subscriptions_webhook(request):
    event_json = json.loads(request.body)

    # Verify the event by fetching it from Stripe

    try:
        # firstly verify this is a real event generated by Stripe.com
        # commented out for testing - uncomment when live
        # event = stripe.Event.retrieve(event_json['object']['id'])

        cust = event_json['object']['customer']
        paid = event_json['object']['paid']
        userProfile = UserProfile.objects.get(stripe_id=cust)

        if userProfile and paid:
            userProfile.subscription_end = arrow.now().replace(weeks=+4).datetime  # add 4 weeks from now
            userProfile.save()

    except (stripe.InvalidRequestError, e):
        return HttpResponse(status=404)

    return HttpResponse(status=200)